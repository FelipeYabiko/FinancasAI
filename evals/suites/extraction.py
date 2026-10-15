"""Extraction suite: precision/recall of transactions (matched by date + amount), per-field
accuracy, parsing failure rate, cost per statement and latency p50/p95."""

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from app.domain.dedup import description_similarity
from app.domain.normalize import normalize_description
from app.services.importer.extraction import extract_transactions
from app.services.importer.pdf_text import extract_pdf_text
from evals.common import DATASETS, PRIVATE, CallLog, ModelSpec, md_table, p50, p95, ratio

DATE_TOLERANCE_DAYS = 3
DESC_THRESHOLD = 0.8


def load_documents(
    subset: str | None = None, limit: int | None = None, include_private: bool = True
):
    docs = []
    for pdf in sorted((DATASETS / "extraction").glob("*.pdf")):
        docs.append((pdf, json.loads(pdf.with_suffix(".json").read_text()), False))
    if include_private:
        for pdf in sorted(PRIVATE.glob("*.pdf")):
            gt = pdf.with_suffix(".json")
            if gt.exists():
                docs.append((pdf, json.loads(gt.read_text()), True))
    if subset == "ci":
        seen, picked = set(), []
        for d in docs:  # one statement per layout
            if d[1].get("layout") not in seen and not d[2]:
                seen.add(d[1].get("layout"))
                picked.append(d)
        docs = picked
    return docs[:limit] if limit else docs


def skipped_entry(pdf_path, gt: dict, private: bool, reason: str) -> dict:
    return {
        "id": "private" if private else Path(pdf_path).stem,
        "layout": gt.get("layout", "private"),
        "tp": 0,
        "fp": 0,
        "fn": len(gt["transactions"]),
        "fields": {},
        "installments": 0,
        "skipped": reason,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }


def match(pred: list[dict], gold: list[dict]) -> list[tuple[int, int]]:
    """Greedy matching by |amount| and date (± tolerance). Returns (gold_idx, pred_idx)."""
    used: set[int] = set()
    pairs = []
    for gi, g in enumerate(gold):
        gd = date.fromisoformat(g["date"])
        best, best_key = None, None
        for pi, p in enumerate(pred):
            if pi in used or abs(p["amount_cents"]) != abs(g["amount_cents"]):
                continue
            delta = abs((date.fromisoformat(p["date"]) - gd).days)
            if delta > DATE_TOLERANCE_DAYS:
                continue
            sim = description_similarity(
                normalize_description(p["description"]), normalize_description(g["description"])
            )
            key = (delta == 0, p["amount_cents"] == g["amount_cents"], sim)
            if best_key is None or key > best_key:
                best, best_key = pi, key
        if best is not None:
            used.add(best)
            pairs.append((gi, best))
    return pairs


def score_document(pred: list[dict], gold: list[dict]) -> dict:
    pairs = match(pred, gold)
    fields = defaultdict(int)
    inst_total = 0
    for gi, pi in pairs:
        g, p = gold[gi], pred[pi]
        fields["date"] += p["date"] == g["date"]
        fields["amount"] += p["amount_cents"] == g["amount_cents"]
        fields["type"] += p["type"] == g["type"]
        sim = description_similarity(
            normalize_description(p["description"]), normalize_description(g["description"])
        )
        fields["description"] += sim >= DESC_THRESHOLD
        if g.get("installment_total"):
            inst_total += 1
            fields["installment"] += (p.get("installment_number"), p.get("installment_total")) == (
                g["installment_number"],
                g["installment_total"],
            )
    return {
        "tp": len(pairs),
        "fp": len(pred) - len(pairs),
        "fn": len(gold) - len(pairs),
        "fields": dict(fields),
        "installments": inst_total,
    }


def aggregate(all_docs: list[dict]) -> dict:
    # Documents hit by provider errors (rate limits, quota) say nothing about the model: they are
    # reported as skipped instead of being scored as misses.
    docs = [d for d in all_docs if not d.get("skipped")]
    tp = sum(d["tp"] for d in docs)
    fp = sum(d["fp"] for d in docs)
    fn = sum(d["fn"] for d in docs)
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None  # nothing scored (e.g. every document skipped)
    else:
        f1 = ratio(2 * precision * recall, precision + recall) if precision and recall else 0.0
    fields = defaultdict(int)
    inst = 0
    for d in docs:
        for k, v in d["fields"].items():
            fields[k] += v
        inst += d["installments"]
    chunks = sum(d.get("chunks", 0) for d in docs)
    failed = sum(d.get("failed_chunks", 0) for d in docs)
    lat = [d["latency_ms"] for d in docs if not d.get("error")]
    costs = [d["cost_usd"] for d in docs]
    return {
        "documents": len(docs),
        "documents_skipped": len(all_docs) - len(docs),
        "documents_failed": sum(1 for d in docs if d.get("error")),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "acc_date": ratio(fields["date"], tp),
        "acc_amount": ratio(fields["amount"], tp),
        "acc_description": ratio(fields["description"], tp),
        "acc_type": ratio(fields["type"], tp),
        "acc_installment": ratio(fields["installment"], inst),
        "parse_failure_rate": ratio(failed, chunks) if chunks else None,
        "cost_per_statement_usd": round(sum(costs) / len(costs), 6) if costs else 0.0,
        "latency_p50_ms": p50(lat),
        "latency_p95_ms": p95(lat),
        "validation_retries": sum(d.get("validation_retries", 0) for d in docs),
    }


def run_model(
    spec: ModelSpec, docs, prompt_version: str | None = None, chunk_tokens: int = 1500
) -> dict:
    per_doc = []
    quota_exhausted = False
    for pdf_path, gt, private in docs:
        if quota_exhausted:
            per_doc.append(skipped_entry(pdf_path, gt, private, "quota_exhausted"))
            continue
        log = CallLog()
        entry = {
            "id": "private" if private else pdf_path.stem,
            "layout": gt.get("layout", "private"),
            "tp": 0,
            "fp": 0,
            "fn": len(gt["transactions"]),
            "fields": {},
            "installments": 0,
        }
        try:
            pdf = extract_pdf_text(Path(pdf_path).read_bytes())
            run = extract_transactions(
                pdf,
                log.client(),
                spec.provider,
                spec.model,
                prompt_version=prompt_version,
                chunk_tokens=chunk_tokens,
            )
            pred = [t.model_dump(mode="json") for t in run.transactions]
            entry.update(score_document(pred, gt["transactions"]))
            entry.update(
                chunks=run.chunks,
                failed_chunks=run.failed_chunks,
                latency_ms=run.latency_ms,
                validation_retries=run.validation_retries,
                warnings=run.warnings,
            )
            if run.provider_failed_chunks:
                entry["skipped"] = "quota_exhausted" if run.quota_exhausted else "provider_error"
                quota_exhausted = run.quota_exhausted
        except Exception as exc:  # a model blowing up on one document must not stop the run
            entry.update(
                error=f"{exc.__class__.__name__}: {str(exc)[:200]}",
                latency_ms=0,
                chunks=1,
                failed_chunks=1,
            )
        entry["cost_usd"] = round(log.cost, 6)
        per_doc.append(entry)
        print(
            f"  {spec.label:45} {entry['id']:14} tp={entry['tp']:3} fp={entry['fp']:3} fn={entry['fn']:3}"
            f" {entry.get('error', '')}{' SKIPPED (' + entry['skipped'] + ')' if entry.get('skipped') else ''}"
        )
        if quota_exhausted:
            print("  ⚠ provider quota exhausted: remaining documents are skipped, not scored")
        for w in entry.get("warnings", [])[:3]:
            print(f"      ⚠ {w[:300]}")
    by_layout = defaultdict(list)
    for d in per_doc:
        by_layout[d["layout"]].append(d)
    return {
        **aggregate(per_doc),
        "per_layout": {
            k: {m: aggregate(v)[m] for m in ("f1", "precision", "recall", "acc_amount")}
            for k, v in sorted(by_layout.items())
            if any(not d.get("skipped") for d in v)
        },
        "per_document": per_doc,
    }


HEADLINE = [
    "f1",
    "precision",
    "recall",
    "acc_date",
    "acc_amount",
    "acc_description",
    "acc_type",
    "parse_failure_rate",
    "cost_per_statement_usd",
    "latency_p50_ms",
    "latency_p95_ms",
]


def markdown(results: dict) -> str:
    rows = [[label, *(r[m] for m in HEADLINE)] for label, r in results.items()]
    out = ["### Extraction", "", md_table(["model", *HEADLINE], rows), ""]
    layouts = sorted({lay for r in results.values() for lay in r["per_layout"]})
    rows = [
        [label, *(r["per_layout"].get(lay, {}).get("f1") for lay in layouts)]
        for label, r in results.items()
    ]
    out += ["F1 by layout:", "", md_table(["model", *layouts], rows), ""]
    return "\n".join(out)
