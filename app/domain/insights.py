"""Deterministic insight calculations (pure functions). The LLM only narrates the results."""

import calendar
import itertools
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.summary import TxLike

# ---------------------------------------------------------------- subscriptions
MIN_OCCURRENCES = 3
INTERVAL_DAYS = (25, 35)
AMOUNT_TOLERANCE = 0.15
# Rent, school fees etc. are monthly too, but they are commitments, not "subscriptions to review".
MAX_SUBSCRIPTION_CENTS = 50_000


def is_installment(t) -> bool:
    return bool(getattr(t, "installment_total", None))


@dataclass
class Subscription:
    merchant: str
    display_name: str
    amount_cents: int  # typical (median) charge
    occurrences: int
    last_date: date
    next_expected: date


def detect_subscriptions(txs: Iterable[TxLike], on: date) -> list[Subscription]:
    """Same merchant, similar amount (±15% of the median), roughly monthly (25–35 days apart),
    at least 3 charges, the latest one not older than ~45 days (still active), up to R$ 500.
    Installment purchases are excluded (they end by themselves)."""
    groups: dict[str, list[TxLike]] = defaultdict(list)
    for t in txs:
        if (
            t.type == "expense"
            and t.amount_cents < 0
            and t.description_normalized
            and not is_installment(t)
        ):
            groups[t.description_normalized].append(t)
    out = []
    for merchant, items in groups.items():
        items.sort(key=lambda t: t.date)
        # one charge per month: collapse same-month duplicates by keeping the first
        monthly: list[TxLike] = []
        for t in items:
            if not monthly or (t.date.year, t.date.month) != (
                monthly[-1].date.year,
                monthly[-1].date.month,
            ):
                monthly.append(t)
        if len(monthly) < MIN_OCCURRENCES:
            continue
        amounts = [-t.amount_cents for t in monthly]
        median = statistics.median(amounts)
        if median > MAX_SUBSCRIPTION_CENTS:
            continue
        if any(abs(a - median) > median * AMOUNT_TOLERANCE for a in amounts[-MIN_OCCURRENCES:]):
            continue
        gaps = [(b.date - a.date).days for a, b in itertools.pairwise(monthly)]
        recent = gaps[-(MIN_OCCURRENCES - 1) :]
        if not all(INTERVAL_DAYS[0] <= g <= INTERVAL_DAYS[1] for g in recent):
            continue
        last = monthly[-1].date
        if (on - last).days > 45:
            continue
        out.append(
            Subscription(
                merchant=merchant,
                display_name=getattr(monthly[-1], "description", merchant),
                amount_cents=int(median),
                occurrences=len(monthly),
                last_date=last,
                next_expected=last + timedelta(days=round(statistics.mean(recent))),
            )
        )
    out.sort(key=lambda s: s.amount_cents, reverse=True)
    return out


# ---------------------------------------------------------------- anomalies
@dataclass
class Anomaly:
    category_id: int | None
    current_cents: int
    average_cents: int
    change_pct: float


def detect_anomalies(
    spend: dict[int | None, list[int]],
    min_ratio: float = 1.3,
    min_delta_cents: int = 5000,
) -> list[Anomaly]:
    """`spend[category] = [m-3, m-2, m-1, current]` expense totals. Flags categories whose
    current month exceeds the 3-month average by ≥30% and by at least R$ 50."""
    out = []
    for cat, series in spend.items():
        *prev, current = series
        if len(prev) < 3:
            continue
        avg = sum(prev[-3:]) // 3
        if avg <= 0:
            continue
        if current >= avg * min_ratio and current - avg >= min_delta_cents:
            out.append(Anomaly(cat, current, avg, round((current - avg) / avg * 100, 1)))
    out.sort(key=lambda a: a.current_cents - a.average_cents, reverse=True)
    return out


# ---------------------------------------------------------------- budget projection
@dataclass
class BudgetProjection:
    category_id: int
    limit_cents: int
    spent_cents: int
    projected_cents: int
    exceeds_on: date | None  # day the pace crosses the limit (None if it doesn't)


def project_budget(category_id: int, spent: int, limit: int, on: date) -> BudgetProjection:
    """Linear projection of month-to-date spending to the end of the month."""
    days = calendar.monthrange(on.year, on.month)[1]
    elapsed = on.day
    projected = spent * days // elapsed if elapsed else spent
    exceeds_on = None
    if spent >= limit:
        exceeds_on = on
    elif projected > limit and spent > 0:
        # first day d where spent * d / elapsed >= limit (integer ceil)
        day = min(days, -(-limit * elapsed // spent))
        exceeds_on = date(on.year, on.month, max(day, on.day))
    return BudgetProjection(category_id, limit, spent, projected, exceeds_on)


# ---------------------------------------------------------------- balance forecast
@dataclass
class Forecast:
    current_cents: int
    recurring_income_cents: int
    recurring_expense_cents: int
    scheduled_cents: int  # future-dated transactions already in the ledger (this month)
    invoices_due_cents: int
    projected_cents: int
    end_of_month: date


def forecast_balance(
    current_cents: int,
    recurring: Iterable[tuple[date, int]],
    scheduled: Iterable[int],
    invoices_due: Iterable[int],
    end_of_month: date,
) -> Forecast:
    """End-of-month balance of cash accounts = today's balance + remaining recurring entries
    (signed) + future-dated entries already registered (signed) − card invoices due this month."""
    rec = list(recurring)
    inc = sum(a for _, a in rec if a > 0)
    exp = sum(-a for _, a in rec if a < 0)
    sched = sum(scheduled)
    inv = sum(invoices_due)
    return Forecast(
        current_cents, inc, exp, sched, inv, current_cents + inc - exp + sched - inv, end_of_month
    )
