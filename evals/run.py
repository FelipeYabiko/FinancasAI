"""Eval runner.

    uv run python -m evals.run --suite extraction --models groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash-lite
    uv run python -m evals.run --suite all                    # models from evals/config.yaml
    uv run python -m evals.run --suite all --subset ci --models fake:fake
    uv run python -m evals.run --suite extraction --update-baseline

Writes evals/results/<date>_<suite>.json/.md, refreshes evals/results/latest.md and compares
against evals/baseline.json (exit code 1 on regressions when --fail-on-regression).
"""

import argparse
import json
import sys

import yaml

from app.llm.providers import available_providers
from evals.common import RESULTS, ROOT, ModelSpec, run_metadata, write_result
from evals.report import build_latest
from evals.suites import agent, baseline, categorization, extraction, injection

SUITES = ["extraction", "categorization", "agent", "baseline", "injection"]
BASELINE_FILE = ROOT / "baseline.json"
LOWER_IS_BETTER = {
    "cost_per_statement_usd",
    "cost_per_case_usd",
    "latency_p50_ms",
    "latency_p95_ms",
    "parse_failure_rate",
    "avg_steps",
    "cost_usd",
}


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def headline(suite: str, r: dict) -> dict:
    if suite == "categorization":
        return {
            "accuracy_without_memory": r["without_memory"]["accuracy"],
            "accuracy_with_memory": r["with_memory"]["accuracy"],
            "cost_usd": r["without_memory"]["cost_usd"],
        }
    keys = {"agent": agent.HEADLINE, "injection": injection.HEADLINE}.get(
        suite, extraction.HEADLINE
    )
    return {k: r.get(k) for k in keys}


def compare(suite: str, results: dict, cfg: dict) -> list[str]:
    if not BASELINE_FILE.exists():
        return []
    base = json.loads(BASELINE_FILE.read_text()).get(suite, {})
    th = cfg.get("regression", {})
    flags = []
    for label, r in results.items():
        old = base.get(label)
        if not old:
            continue
        for metric, new_v in headline(suite, r).items():
            old_v = old.get(metric)
            if old_v is None or new_v is None:
                continue
            if metric in LOWER_IS_BETTER:
                if old_v > 0 and (new_v - old_v) / old_v > th.get("cost_increase", 0.5):
                    flags.append(f"{suite} · {label} · {metric}: {old_v} → {new_v}")
            elif old_v - new_v > th.get("rate_drop", 0.03):
                flags.append(f"{suite} · {label} · {metric}: {old_v} → {new_v}")
    return flags


def update_baseline(suite: str, results: dict) -> None:
    data = json.loads(BASELINE_FILE.read_text()) if BASELINE_FILE.exists() else {}
    data.setdefault(suite, {})
    for label, r in results.items():
        data[suite][label] = headline(suite, r)
    BASELINE_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def _versions(args) -> list[str | None]:
    """`--prompt-version v1,v2` compares versions side by side; default = the app's default."""
    return args.prompt_version.split(",") if args.prompt_version else [None]


def _label(m: ModelSpec, suite: str, version: str | None) -> str:
    return m.label if version is None else f"{m.label} @{suite}.{version}"


def run_suite(suite: str, models: list[ModelSpec], args) -> dict:
    print(f"\n=== {suite} ===")
    if suite == "baseline":
        docs = extraction.load_documents(args.subset, args.limit)
        results = {"regex-baseline": baseline.run(docs)}
        md = extraction.markdown(results).replace(
            "### Extraction", "### Baseline (regex parser, no LLM)"
        )
    elif suite == "extraction":
        docs = extraction.load_documents(args.subset, args.limit)
        results = {
            _label(m, suite, v): extraction.run_model(m, docs, v)
            for m in models
            for v in _versions(args)
        }
        md = extraction.markdown(results)
    elif suite == "categorization":
        items = categorization.load_items(args.subset, args.limit)
        results = {m.label: categorization.run_model(m, items) for m in models}
        md = categorization.markdown(results, len(items))
    elif suite == "agent":
        data = agent.load_cases(args.subset, args.limit)
        results = {
            _label(m, suite, v): agent.run_model(m, data, v)
            for m in models
            for v in _versions(args)
        }
        md = agent.markdown(results)
    elif suite == "injection":
        docs = injection.load_documents()
        results = {
            _label(m, "extraction", v): injection.run_model(m, docs, v)
            for m in models
            for v in _versions(args)
        }
        md = injection.markdown(results)
    else:
        raise SystemExit(f"unknown suite {suite}")
    meta = {**run_metadata(suite), "subset": args.subset, "limit": args.limit}
    if args.prompt_version:
        meta["prompt_versions"] = {**meta["prompt_versions"], suite: args.prompt_version}
    if suite == "categorization":
        meta["items"] = len(items)
    payload = {"meta": meta, "results": results}
    path = write_result(suite, payload, md)
    print(md)
    print(f"→ {path.relative_to(ROOT.parent)}")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--suite", default="all", help=f"{', '.join(SUITES)} or all")
    ap.add_argument("--models", help="comma-separated provider:model (default: evals/config.yaml)")
    ap.add_argument("--subset", choices=["ci"], help="small subset (CI)")
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--prompt-version", help="e.g. v2, or v1,v2 to compare side by side (default: app default)"
    )
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--fail-on-regression", action="store_true")
    ap.add_argument(
        "--skip-unavailable", action="store_true", help="skip models whose provider has no key"
    )
    args = ap.parse_args(argv)
    cfg = load_config()
    names = (
        args.models.split(",")
        if args.models
        else cfg["ci_models" if args.subset == "ci" else "models"]
    )
    models = [ModelSpec.parse(n) for n in names]
    avail = available_providers()
    suites = SUITES if args.suite == "all" else args.suite.split(",")
    if set(suites) == {"baseline"}:
        models = []  # the regex baseline calls no LLM, so no key is needed
    missing = [m for m in models if not avail.get(m.provider)]
    if missing:
        msg = "no API key for: " + ", ".join(m.label for m in missing)
        if args.skip_unavailable:
            print(f"skipping ({msg})")
            models = [m for m in models if m not in missing]
        else:
            print(
                f"error: {msg}. Set the keys in .env or pass --skip-unavailable.", file=sys.stderr
            )
            return 2
    flags = []
    for suite in suites:
        if suite != "baseline" and not models:
            print(f"skipping {suite}: no models available")
            continue
        results = run_suite(suite, models, args)
        flags += compare(suite, results, cfg)
        if args.update_baseline:
            update_baseline(suite, results)
    latest = build_latest(RESULTS)
    print(f"\nreport → {latest.relative_to(ROOT.parent)}")
    if flags:
        print("\n⚠️  REGRESSIONS vs evals/baseline.json:")
        for f in flags:
            print("  -", f)
        return 1 if args.fail_on_regression else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
