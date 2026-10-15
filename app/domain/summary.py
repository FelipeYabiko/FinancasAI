"""Aggregations over transactions. Transfers never count as income or expense.

Sign convention: `amount_cents` is signed (money in > 0, money out < 0). A refund
on an expense is an `expense` with a positive amount, so it reduces expenses.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

WEEKDAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


class TxLike(Protocol):
    date: date
    amount_cents: int
    type: str
    category_id: int | None
    description_normalized: str


@dataclass
class Totals:
    income_cents: int = 0
    expense_cents: int = 0
    count: int = 0

    @property
    def net_cents(self) -> int:
        return self.income_cents - self.expense_cents


def totals(txs: Iterable[TxLike]) -> Totals:
    t = Totals()
    for tx in txs:
        t.count += 1
        if tx.type == "income":
            t.income_cents += tx.amount_cents
        elif tx.type == "expense":
            t.expense_cents += -tx.amount_cents
    return t


def expenses_by_category(txs: Iterable[TxLike]) -> dict[int | None, int]:
    out: dict[int | None, int] = defaultdict(int)
    for tx in txs:
        if tx.type == "expense":
            out[tx.category_id] += -tx.amount_cents
    return dict(out)


def expenses_by_weekday(txs: Iterable[TxLike]) -> list[int]:
    out = [0] * 7
    for tx in txs:
        if tx.type == "expense":
            out[tx.date.weekday()] += -tx.amount_cents
    return out


def top_merchants(txs: Iterable[TxLike], limit: int = 5) -> list[tuple[str, int, int]]:
    """(normalized description, total spent, count), biggest first."""
    spent: dict[str, int] = defaultdict(int)
    count: dict[str, int] = defaultdict(int)
    for tx in txs:
        if tx.type == "expense" and tx.description_normalized:
            spent[tx.description_normalized] += -tx.amount_cents
            count[tx.description_normalized] += 1
    ranked = sorted(spent.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [(k, v, count[k]) for k, v in ranked]


def pct_change(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 1)
