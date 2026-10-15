"""Dashboard aggregations (read-only)."""

from datetime import date

from sqlmodel import Session, select

from app.domain import summary
from app.domain.dates import add_months_to_month, month_bounds, month_key, today
from app.domain.invoices import invoice_due_date
from app.models import Account, Budget, Category, Transaction
from app.services.ledger import account_balances


def _month_txs(session: Session, month: str) -> list[Transaction]:
    start, end = month_bounds(month)
    return list(
        session.exec(select(Transaction).where(Transaction.date >= start, Transaction.date <= end))
    )


def budget_status(spent: int, limit: int) -> tuple[float, str]:
    pct = round(spent / limit * 100, 1) if limit else 0.0
    status = "exceeded" if pct >= 100 else "warning" if pct >= 80 else "ok"
    return pct, status


def budgets_for_month(session: Session, month: str) -> list[dict]:
    by_cat = summary.expenses_by_category(_month_txs(session, month))
    out = []
    for b in session.exec(select(Budget).where(Budget.month == month)):
        spent = by_cat.get(b.category_id, 0)
        pct, status = budget_status(spent, b.limit_cents)
        out.append(
            {
                "id": b.id,
                "category_id": b.category_id,
                "month": b.month,
                "limit_cents": b.limit_cents,
                "spent_cents": spent,
                "percent": pct,
                "status": status,
            }
        )
    return out


def open_invoices(session: Session, on: date | None = None) -> list[dict]:
    """Credit card invoices whose due date hasn't passed yet, with their amount."""
    on = on or today()
    out = []
    cards = session.exec(select(Account).where(Account.type == "credit_card"))
    for card in cards:
        rows = session.exec(
            select(Transaction).where(
                Transaction.account_id == card.id,
                Transaction.invoice_month != None,  # noqa: E711
                Transaction.type != "transfer",
            )
        )
        per_invoice: dict[str, int] = {}
        for tx in rows:
            per_invoice[tx.invoice_month] = per_invoice.get(tx.invoice_month, 0) - tx.amount_cents
        for inv in sorted(per_invoice):
            due = invoice_due_date(inv, card.closing_day or 1, card.due_day or 1)
            if due < on or per_invoice[inv] == 0:
                continue
            out.append(
                {
                    "account_id": card.id,
                    "account_name": card.name,
                    "invoice_month": inv,
                    "amount_cents": per_invoice[inv],
                    "due_date": due.isoformat(),
                }
            )
    out.sort(key=lambda x: x["due_date"])
    return out


def dashboard(session: Session, month: str | None = None) -> dict:
    month = month or month_key(today())
    cats = {c.id: c for c in session.exec(select(Category))}
    txs = _month_txs(session, month)
    t = summary.totals(txs)
    prev = summary.totals(_month_txs(session, add_months_to_month(month, -1)))

    series = []
    for i in range(5, -1, -1):
        m = add_months_to_month(month, -i)
        mt = t if i == 0 else summary.totals(_month_txs(session, m))
        series.append(
            {"month": m, "income_cents": mt.income_cents, "expense_cents": mt.expense_cents}
        )

    by_cat = summary.expenses_by_category(txs)
    by_category = sorted(
        (
            {
                "category_id": cid,
                "name": cats[cid].name if cid in cats else "Sem categoria",
                "color": cats[cid].color if cid in cats else "#94a3b8",
                "icon": cats[cid].icon if cid in cats else "❔",
                "amount_cents": amt,
            }
            for cid, amt in by_cat.items()
            if amt > 0
        ),
        key=lambda x: x["amount_cents"],
        reverse=True,
    )
    _, month_end = month_bounds(month)
    balances = account_balances(session, until=min(month_end, today()))
    accounts = [
        {
            "id": a.id,
            "name": a.name,
            "type": a.type,
            "color": a.color,
            "balance_cents": balances[a.id],
        }
        for a in session.exec(select(Account).where(Account.archived == False))  # noqa: E712
    ]
    return {
        "month": month,
        "income_cents": t.income_cents,
        "expense_cents": t.expense_cents,
        "net_cents": t.net_cents,
        "income_change_pct": summary.pct_change(t.income_cents, prev.income_cents),
        "expense_change_pct": summary.pct_change(t.expense_cents, prev.expense_cents),
        "accounts": accounts,
        "total_balance_cents": sum(a["balance_cents"] for a in accounts),
        "by_category": by_category,
        "last_6_months": series,
        "top_merchants": [
            {"name": n, "amount_cents": a, "count": c} for n, a, c in summary.top_merchants(txs)
        ],
        "by_weekday": [
            {"weekday": summary.WEEKDAYS_PT[i], "amount_cents": v}
            for i, v in enumerate(summary.expenses_by_weekday(txs))
        ],
        "open_invoices": open_invoices(session),
        "budgets": budgets_for_month(session, month),
    }
