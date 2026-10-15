"""Baseline suite: deterministic regex parser vs. ground truth (no LLM, zero cost).

The parser targets the "aurora" layout; scores on the other layouts show how a hand-written
parser degrades on unseen formats, which is the point of the LLM vs. regex comparison."""

import time
from collections import defaultdict
from pathlib import Path

from app.services.importer.baseline import parse_lines
from app.services.importer.chunking import strip_repeated_boilerplate
from app.services.importer.detect import detect_document
from app.services.importer.pdf_text import extract_pdf_text
from evals.suites.extraction import aggregate, score_document


def run(docs) -> dict:
    per_doc = []
    for pdf_path, gt, private in docs:
        started = time.perf_counter()
        pdf = extract_pdf_text(Path(pdf_path).read_bytes())
        info = detect_document(pdf.lines)
        pages, _ = strip_repeated_boilerplate(pdf.pages)
        pred = parse_lines([ln for p in pages for ln in p], info.reference_year)
        entry = {
            "id": "private" if private else pdf_path.stem,
            "layout": gt.get("layout", "private"),
            **score_document(pred, gt["transactions"]),
            "cost_usd": 0.0,
            "chunks": 1,
            "failed_chunks": 0,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
        per_doc.append(entry)
    by_layout = defaultdict(list)
    for d in per_doc:
        by_layout[d["layout"]].append(d)
    return {
        **aggregate(per_doc),
        "per_layout": {
            k: {m: aggregate(v)[m] for m in ("f1", "precision", "recall", "acc_amount")}
            for k, v in sorted(by_layout.items())
        },
        "per_document": per_doc,
    }
