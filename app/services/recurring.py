"""Materialize recurring rules into transactions (idempotent)."""

from datetime import date

from sqlmodel import Session, select

from app.domain.dates import month_key, today
from app.domain.invoices import invoice_month
from app.domain.normalize import normalize_description
from app.domain.recurring import months_to_generate, occurrence_date
from app.models import Account, RecurringRule, Transaction
from app.services.ledger import signed_amount


def run_recurring(session: Session, on: date | None = None) -> list[Transaction]:
    """Create the missing transactions of every active rule up to the current
    month. Uses (recurring_rule_id, recurring_month) as the idempotency key, so
    running it repeatedly never duplicates."""
    current = month_key(on or today())
    created: list[Transaction] = []
    rules = session.exec(select(RecurringRule).where(RecurringRule.active == True))  # noqa: E712
    for rule in rules:
        existing = set(
            session.exec(
                select(Transaction.recurring_month).where(Transaction.recurring_rule_id == rule.id)
            )
        )
        acc = session.get(Account, rule.account_id)
        if not acc:
            continue
        for month in months_to_generate(rule.start_month, current, existing):
            d = occurrence_date(month, rule.day_of_month)
            tx = Transaction(
                date=d,
                description=rule.description,
                description_normalized=normalize_description(rule.description),
                amount_cents=signed_amount(rule.amount_cents, rule.type),
                type=rule.type,
                category_id=rule.category_id,
                account_id=acc.id,
                invoice_month=(
                    invoice_month(d, acc.closing_day)
                    if acc.type == "credit_card" and acc.closing_day
                    else None
                ),
                origin="recurring",
                recurring_rule_id=rule.id,
                recurring_month=month,
            )
            session.add(tx)
            created.append(tx)
    if created:
        session.commit()
    return created
