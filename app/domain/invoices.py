"""Credit card invoice rules."""

from datetime import date

from app.domain.dates import add_months_to_month, clamp_day, month_key, parse_month


def invoice_month(purchase: date, closing_day: int) -> str:
    """Invoice ('YYYY-MM') a credit card purchase belongs to.

    A purchase made on or before the closing day goes to that month's invoice;
    after the closing day it goes to the next month's invoice. The closing day
    is clamped to the month length (closing day 31 closes on Feb 28/29).
    """
    closing = clamp_day(purchase.year, purchase.month, closing_day)
    month = month_key(purchase)
    if purchase <= closing:
        return month
    return add_months_to_month(month, 1)


def invoice_closing_date(invoice: str, closing_day: int) -> date:
    y, m = parse_month(invoice)
    return clamp_day(y, m, closing_day)


def invoice_due_date(invoice: str, closing_day: int, due_day: int) -> date:
    """Due date of an invoice. If the due day is not after the closing day, the
    payment falls in the month after the closing (e.g. closes 25, due 5)."""
    month = invoice if due_day > closing_day else add_months_to_month(invoice, 1)
    y, m = parse_month(month)
    return clamp_day(y, m, due_day)
