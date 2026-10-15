"""Builds evals/results/latest.md from the most recent result file of each suite."""

import json
from pathlib import Path

from evals.common import md_table
from evals.suites import agent, categorization, extraction

NOTE_FAKE = (
    "`fake:fake` is the offline stand-in provider (regex parser for extraction, keyword rules for "
    "categorization, a rule-based toy for the agent). It is **not an LLM**; it shows the deterministic floor "
    "and proves the harness runs end to end without API keys."
)


def _latest(results_dir: Path, suite: str) -> dict | None:
    files = sorted(results_dir.glob(f"*_{suite}.json"))
    return json.loads(files[-1].read_text()) if files else None


def _is_llm(label: str) -> bool:
    return not label.startswith("fake:") and label != "regex-baseline"


def _pick(
    rows: dict[str, dict], quality: str, cost: str, tolerance: float = 0.02
) -> tuple[str, str] | None:
    """(best-quality model, cheapest model within `tolerance` of the best)."""
    cands = {k: v for k, v in rows.items() if _is_llm(k) and v.get(quality) is not None}
    if not cands:
        return None
    best = max(cands, key=lambda k: cands[k][quality])
    good = [k for k in cands if cands[k][quality] >= cands[best][quality] - tolerance]
    cheapest = min(good, key=lambda k: (cands[k].get(cost) or 0, -cands[k][quality]))
    return best, cheapest


def conclusion(ext: dict, cat: dict, ag: dict) -> str:
    parts = []
    llms = sorted({k for k in (*ext, *cat, *ag) if _is_llm(k)})
    if len(llms) == 1:
        m = llms[0]
        bits = []
        if m in ext:
            e = ext[m]
            bits.append(
                f"extraction F1 {e['f1']} on {e['documents']} statements "
                f"(US$ {e['cost_per_statement_usd']}/statement, p95 {e['latency_p95_ms']} ms)"
            )
        if m in cat:
            bits.append(f"categorization accuracy {cat[m]['without_memory']['accuracy']}")
        if m in ag:
            bits.append(f"agent pass rate {ag[m]['pass_rate']} on {ag[m]['cases']} cases")
        return (
            f"Only one LLM has been evaluated so far: `{m}` — {'; '.join(bits)}. "
            "No model choice can be made from a single data point; the multi-model comparison is pending "
            "(run `uv run python -m evals.run --suite all` with keys for other providers)."
        )
    if ext:
        pick = _pick(ext, "f1", "cost_per_statement_usd")
        if pick:
            best, cheap = pick
            b, c = ext[best], ext[cheap]
            if best == cheap:
                parts.append(
                    f"**Extraction:** `{best}` has the best F1 ({b['f1']}) and is also the cheapest model "
                    f"within 2 points of it (US$ {b['cost_per_statement_usd']}/statement, p95 {b['latency_p95_ms']} ms)."
                )
            else:
                parts.append(
                    f"**Extraction:** `{best}` has the best F1 ({b['f1']}), but `{cheap}` is within 2 points "
                    f"(F1 {c['f1']}) at US$ {c['cost_per_statement_usd']} vs {b['cost_per_statement_usd']} per "
                    f"statement → use `{cheap}` by default."
                )
    if cat:
        flat = {
            k: {
                "acc": v["without_memory"]["accuracy"],
                "cost": v["without_memory"]["cost_usd"],
                "mem": v["with_memory"]["accuracy"],
            }
            for k, v in cat.items()
        }
        pick = _pick(flat, "acc", "cost")
        if pick:
            best, cheap = pick
            parts.append(
                f"**Categorization:** best accuracy `{best}` ({flat[best]['acc']}); cheapest within 2 points: "
                f"`{cheap}` ({flat[cheap]['acc']}). The deterministic memory raises accuracy to "
                f"{flat[cheap]['mem']} and removes those items from the LLM bill."
            )
    if ag:
        pick = _pick(ag, "pass_rate", "cost_per_case_usd", tolerance=0.034)
        if pick:
            best, cheap = pick
            parts.append(
                f"**Assistant:** `{best}` passes {ag[best]['pass_rate']} of the cases "
                f"(asks when ambiguous: {ag[best]['ask_when_ambiguous']}); "
                + (
                    f"`{cheap}` is the cheaper option within one case."
                    if cheap != best
                    else "it is also the cheapest of the top group."
                )
            )
    if not parts:
        return (
            "_No real LLM has been evaluated yet in this results folder (only the offline baseline/fake "
            "provider). Configure API keys in `.env` and run `uv run python -m evals.run --suite all` to fill "
            "the comparison; this paragraph is generated from the measured numbers._"
        )
    return "\n\n".join(parts)


def build_latest(results_dir: Path) -> Path:
    ext_run = _latest(results_dir, "extraction")
    cat_run = _latest(results_dir, "categorization")
    ag_run = _latest(results_dir, "agent")
    base_run = _latest(results_dir, "baseline")
    ext = ext_run["results"] if ext_run else {}
    cat = cat_run["results"] if cat_run else {}
    ag = ag_run["results"] if ag_run else {}
    base = base_run["results"] if base_run else {}

    models = list(dict.fromkeys([*ext, *cat, *ag]))
    rows = []
    for m in models:
        e, c, a = ext.get(m, {}), cat.get(m, {}), ag.get(m, {})
        eval_set = " / ".join(
            x
            for x in (
                f"{e['documents']} PDFs" if e else "",
                f"{a['cases']} cases" if a else "",
                f"{len(c.get('without_memory', {}).get('per_category', {}))} categories"
                if c
                else "",
            )
            if x
        )
        rows.append(
            [
                m,
                eval_set,
                e.get("f1"),
                e.get("cost_per_statement_usd"),
                e.get("latency_p95_ms"),
                c.get("without_memory", {}).get("accuracy"),
                c.get("with_memory", {}).get("accuracy"),
                a.get("pass_rate"),
                a.get("cost_per_case_usd"),
            ]
        )
    for label, b in base.items():
        rows.append(
            [
                f"{label} (no LLM)",
                f"{b['documents']} PDFs",
                b["f1"],
                0.0,
                b["latency_p95_ms"],
                None,
                None,
                None,
                None,
            ]
        )

    lines = ["# Eval results (latest)", ""]
    for run, name in (
        (ext_run, "extraction"),
        (cat_run, "categorization"),
        (ag_run, "agent"),
        (base_run, "baseline"),
    ):
        if run:
            m = run["meta"]
            lines.append(
                f"- **{name}**: {m['timestamp']} · commit `{m['git_sha']}` · prompts "
                f"{', '.join(f'{k}.{v}' for k, v in m['prompt_versions'].items() if k != 'ping')}"
                f"{' · subset ' + m['subset'] if m.get('subset') else ''}"
            )
    lines += [
        "",
        "## Comparison",
        "",
        md_table(
            [
                "model",
                "eval set",
                "extraction F1",
                "cost / statement (USD)",
                "extraction p95 (ms)",
                "categ. acc",
                "categ. acc + memory",
                "agent pass rate",
                "cost / agent case (USD)",
            ],
            rows,
        ),
        "",
        "## Conclusion",
        "",
        conclusion(ext, cat, ag),
        "",
    ]
    if any(m.startswith("fake:") for m in models):
        lines += [f"> {NOTE_FAKE}", ""]
    lines += ["## Details", ""]
    if ext:
        lines.append(extraction.markdown(ext))
    if base:
        lines.append(
            extraction.markdown(base).replace(
                "### Extraction", "### Baseline (regex parser, no LLM)"
            )
        )
    if cat:
        lines.append(categorization.markdown(cat, cat_run["meta"].get("items", 0)))
    if ag:
        lines.append(agent.markdown(ag))
    lines += ["## Methodology", "", METHODOLOGY]
    out = results_dir / "latest.md"
    out.write_text("\n".join(lines))
    return out


METHODOLOGY = """\
- **Extraction** — 40 synthetic PDFs (4 fictional layouts, 1,466 transactions) with JSON ground truth
  (`evals/datasets/extraction`). A predicted transaction matches a gold one when |amount| is equal and the
  date is within ±3 days; precision/recall/F1 count matches. Field accuracy is measured on matched pairs:
  exact date, exact signed amount, normalized description similarity ≥ 0.8, exact type. Parse failure rate =
  chunks whose output failed validation twice (or the provider failed) / chunks. Cost comes from token usage ×
  `app/llm/pricing.yaml`; latency is wall-clock per statement (chunks run 4 in parallel).
- **Categorization** — labelled descriptions (`evals/datasets/categorization.json`), scored against the
  default categories. "With memory" pre-loads `CategoryMemory` with one plain descriptor per merchant (what a
  user correction would store) and evaluates every statement variant, so hits depend on normalization.
- **Agent** — cases in `evals/datasets/agent_cases.yaml`, each on a freshly seeded in-memory DB with a fixed
  "today". Checks: proposed write tools and arguments (resolved to ids), DB state after confirming every
  proposal, read tools used for questions, numbers in the answer, asking instead of acting on ambiguous
  requests, and that nothing was written before confirmation.
- **Baseline** — the regex parser (`app/services/importer/baseline.py`), written for the "aurora" layout,
  scored with the same matcher.
- Regressions: `evals/baseline.json` stores headline metrics per suite/model; the runner flags accuracy drops
  > 3 points and cost/latency increases > 50%.
"""
