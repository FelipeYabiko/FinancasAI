"""AI diagnostics: cost, latency percentiles, error rate, recent failures."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, select

from app.models import LLMCall


def percentile(values: list[int], p: float) -> int:
    """Nearest-rank percentile (p in 0..100)."""
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p / 100 * len(s) + 0.5) - 1))
    return s[k]


def diagnostics(db: Session, days: int = 30) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = list(db.exec(select(LLMCall).where(LLMCall.created_at >= since)))
    ok_lat = [r.latency_ms for r in rows if r.status == "ok"]
    by_feature: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0, "errors": 0,
                                                       "input_tokens": 0, "output_tokens": 0,
                                                       "latencies": []})  # fmt: skip
    per_day: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "cost_usd": 0.0})
    for r in rows:
        f = by_feature[r.feature]
        f["calls"] += 1
        f["cost_usd"] += r.cost_usd
        f["input_tokens"] += r.input_tokens
        f["output_tokens"] += r.output_tokens
        if r.status != "ok":
            f["errors"] += 1
        elif r.latency_ms:
            f["latencies"].append(r.latency_ms)
        day = r.created_at.date().isoformat()
        per_day[day]["calls"] += 1
        per_day[day]["cost_usd"] += r.cost_usd
        if r.status != "ok":
            per_day[day]["errors"] += 1
    features = []
    for name, f in sorted(by_feature.items()):
        lat = f.pop("latencies")
        features.append({"feature": name, **f, "cost_usd": round(f["cost_usd"], 6),
                         "p50_ms": percentile(lat, 50), "p95_ms": percentile(lat, 95)})  # fmt: skip
    failures = db.exec(
        select(LLMCall)
        .where(LLMCall.status != "ok")
        .order_by(col(LLMCall.created_at).desc())
        .limit(10)
    ).all()
    total = len(rows)
    errors = sum(1 for r in rows if r.status != "ok")
    return {
        "days": days,
        "total_calls": total,
        "total_cost_usd": round(sum(r.cost_usd for r in rows), 6),
        "error_rate": round(errors / total * 100, 1) if total else 0.0,
        "p50_ms": percentile(ok_lat, 50),
        "p95_ms": percentile(ok_lat, 95),
        "by_feature": features,
        "per_day": [
            {"day": d, **v, "cost_usd": round(v["cost_usd"], 6)} for d, v in sorted(per_day.items())
        ],
        "recent_failures": [
            {
                "created_at": r.created_at.isoformat(),
                "feature": r.feature,
                "provider": r.provider,
                "model": r.model,
                "prompt_version": r.prompt_version,
                "status": r.status,
                "error_message": r.error_message,
            }
            for r in failures
        ],
        "recent_calls": [
            {
                "created_at": r.created_at.isoformat(),
                "feature": r.feature,
                "provider": r.provider,
                "model": r.model,
                "prompt_version": r.prompt_version,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "status": r.status,
            }
            for r in sorted(rows, key=lambda r: r.created_at, reverse=True)[:20]
        ],
    }
