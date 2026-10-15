"""Installment purchase splitting."""

from dataclasses import dataclass
from datetime import date

from app.domain.dates import add_months, add_months_to_month
from app.domain.invoices import invoice_month


@dataclass(frozen=True)
class Installment:
    number: int
    total: int
    amount_cents: int
    date: date
    invoice_month: str | None


def split_amount(total_cents: int, n: int) -> list[int]:
    """Split `total_cents` into `n` parts; the cent difference goes to the last one.

    The parts always sum exactly to the total.
    """
    if n < 1:
        raise ValueError("installments must be >= 1")
    if total_cents < 0:
        return [-p for p in split_amount(-total_cents, n)]
    base = total_cents // n
    return [base] * (n - 1) + [total_cents - base * (n - 1)]


def plan_installments(
    total_cents: int, n: int, purchase: date, closing_day: int | None
) -> list[Installment]:
    """One installment per consecutive invoice, starting at the purchase's invoice."""
    parts = split_amount(total_cents, n)
    first_invoice = invoice_month(purchase, closing_day) if closing_day else None
    out = []
    for i, amount in enumerate(parts):
        out.append(
            Installment(
                number=i + 1,
                total=n,
                amount_cents=amount,
                date=add_months(purchase, i),
                invoice_month=add_months_to_month(first_invoice, i) if first_invoice else None,
            )
        )
    return out
