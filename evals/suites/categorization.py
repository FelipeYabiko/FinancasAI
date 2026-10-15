"""Categorization suite: accuracy overall and per category, with and without CategoryMemory.

"With memory" simulates a household that already corrected ONE plain descriptor per merchant
(e.g. "UBER *TRIP"). Statement variants ("COMPRA DEBITO UBER *TRIP SAO PAULO BR") only hit the
memory if normalization maps them to the same key, so this also measures normalization."""

import json
from collections import defaultdict

from app.db import DEFAULT_CATEGORIES
from app.domain.normalize import normalize_description
from app.services.importer.categorize import CatItem, categorize
from evals.common import DATASETS, CallLog, ModelSpec, md_table, ratio
from evals.generators.catalog import MERCHANTS

CATEGORIES = [(i + 1, name, kind) for i, (name, kind, _, _) in enumerate(DEFAULT_CATEGORIES)]
NAME_BY_ID = {cid: name for cid, name, _ in CATEGORIES}
ID_BY_NAME = {name: cid for cid, name, _ in CATEGORIES}


def load_items(subset: str | None = None, limit: int | None = None) -> list[dict]:
    items = json.loads((DATASETS / "categorization.json").read_text())
    if subset == "ci":
        items = items[::10]
    return items[:limit] if limit else items


def history_memory() -> dict[str, int]:
    return {normalize_description(names[0]): ID_BY_NAME[cat] for names, cat, _ in MERCHANTS}


def _score(items: list[dict], predicted: list[int | None]) -> dict:
    per_cat = defaultdict(lambda: [0, 0])
    correct = 0
    for it, pred in zip(items, predicted, strict=True):
        ok = NAME_BY_ID.get(pred) == it["category"]
        correct += ok
        per_cat[it["category"]][0] += ok
        per_cat[it["category"]][1] += 1
    return {
        "accuracy": ratio(correct, len(items)),
        "per_category": {k: ratio(c, n) for k, (c, n) in sorted(per_cat.items())},
    }


def run_model(spec: ModelSpec | None, items: list[dict]) -> dict:
    out = {}
    for mode, memory in (("without_memory", {}), ("with_memory", history_memory())):
        log = CallLog()
        run = categorize(
            [CatItem(it["description"], it["type"]) for it in items],
            CATEGORIES,
            memory,
            log.client() if spec else None,
            spec.provider if spec else "",
            spec.model if spec else "",
        )
        scored = _score(items, [r.category_id for r in run.results])
        out[mode] = {
            **scored,
            "from_memory": run.from_memory,
            "from_llm": run.from_llm,
            "llm_calls": len(log.calls),
            "cost_usd": round(log.cost, 6),
            "latency_ms": sum(c.latency_ms for c in log.calls),
            "failures": sum(1 for c in log.calls if c.status != "ok"),
        }
        label = spec.label if spec else "memory-only"
        print(
            f"  {label:45} {mode:15} acc={out[mode]['accuracy']} memory={run.from_memory} llm={run.from_llm}"
        )
    return out


def markdown(results: dict, n_items: int) -> str:
    rows = []
    for label, r in results.items():
        w, wo = r["with_memory"], r["without_memory"]
        rows.append(
            [label, wo["accuracy"], w["accuracy"], w["from_memory"], wo["cost_usd"], w["cost_usd"]]
        )
    head = [
        "model",
        "accuracy (no memory)",
        "accuracy (with memory)",
        "memory hits",
        "cost no-mem (USD)",
        "cost with-mem (USD)",
    ]
    out = [f"### Categorization ({n_items} labelled descriptions)", "", md_table(head, rows), ""]
    cats = sorted({c for r in results.values() for c in r["without_memory"]["per_category"]})
    rows = [
        [c, *(r["without_memory"]["per_category"].get(c) for r in results.values())] for c in cats
    ]
    out += [
        "Per-category accuracy (no memory):",
        "",
        md_table(["category", *results.keys()], rows),
        "",
    ]
    return "\n".join(out)
