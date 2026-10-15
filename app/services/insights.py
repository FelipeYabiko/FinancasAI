"""Insights: deterministic numbers (app/domain/insights.py) + optional LLM narration."""

import json
from datetime import date

from sqlmodel import Session, col, select

from app.domain import summary
from app.domain.dates import add_months_to_month, month_bounds, month_key, today
from app.domain.insights import (
    detect_anomalies,
    detect_subscriptions,
    forecast_balance,
    project_budget,
)
from app.domain.invoices import invoice_closing_date
from app.domain.money import format_brl
from app.llm.client import LLMValidationError
from app.llm.prompts import load_prompt
from app.llm.types import LLMConfigError, ProviderError
from app.models import Account, Budget, Category, Transaction
from app.schemas.llm import InsightTexts
from app.services.ai_config import client_for, feature_config
from app.services.dashboard import open_invoices
from app.services.ledger import account_balances


def _txs_between(db: Session, start: date, end: date) -> list[Transaction]:
    return list(
        db.exec(select(Transaction).where(Transaction.date >= start, Transaction.date <= end))
    )


def compute_insights(db: Session, on: date | None = None) -> list[dict]:
    """Facts with their numbers and a deterministic default text (used when the LLM is off)."""
    on = on or today()
    month = month_key(on)
    cats = {c.id: c for c in db.exec(select(Category))}
    cat_name = lambda cid: cats[cid].name if cid in cats else "Sem categoria"  # noqa: E731
    facts: list[dict] = []

    # 1. subscriptions (look back 6 months)
    six_ago, _ = month_bounds(add_months_to_month(month, -6))
    subs = detect_subscriptions(_txs_between(db, six_ago, on), on)
    if subs:
        total = sum(s.amount_cents for s in subs)
        facts.append(
            {
                "kind": "subscriptions",
                "severity": "info",
                "data": {
                    "count": len(subs),
                    "monthly_total": format_brl(total),
                    "yearly_total": format_brl(total * 12),
                    "items": [
                        {
                            "merchant": s.merchant,
                            "amount": format_brl(s.amount_cents),
                            "next_expected": s.next_expected.isoformat(),
                            "charges": s.occurrences,
                        }
                        for s in subs
                    ],
                },
                "title": f"{len(subs)} assinatura(s) recorrente(s)",
                "body": f"Somam {format_brl(total)} por mês ({format_brl(total * 12)} por ano). Vale revisar se todas ainda fazem sentido.",
            }
        )

    # 2. anomalies: this month vs the 3 previous
    months = [add_months_to_month(month, -i) for i in (3, 2, 1, 0)]
    spend: dict[int | None, list[int]] = {}
    for i, m in enumerate(months):
        start, end = month_bounds(m)
        if m == month:
            end = on
        for cid, v in summary.expenses_by_category(_txs_between(db, start, end)).items():
            spend.setdefault(cid, [0, 0, 0, 0])[i] = v
    for a in detect_anomalies(spend)[:3]:
        facts.append(
            {
                "kind": "anomaly",
                "severity": "warning",
                "data": {
                    "category": cat_name(a.category_id),
                    "current": format_brl(a.current_cents),
                    "average_3_months": format_brl(a.average_cents),
                    "change": f"{a.change_pct:.0f}%",
                },
                "title": f"Gasto alto em {cat_name(a.category_id)}",
                "body": f"{format_brl(a.current_cents)} este mês, {a.change_pct:.0f}% acima da média dos 3 meses anteriores ({format_brl(a.average_cents)}).",
            }
        )

    # 3. budget pace
    start, _ = month_bounds(month)
    by_cat = summary.expenses_by_category(_txs_between(db, start, on))
    for b in db.exec(select(Budget).where(Budget.month == month)):
        p = project_budget(b.category_id, by_cat.get(b.category_id, 0), b.limit_cents, on)
        if not p.exceeds_on:
            continue
        name = cat_name(b.category_id)
        already = p.spent_cents >= p.limit_cents
        facts.append(
            {
                "kind": "budget",
                "severity": "danger" if already else "warning",
                "data": {
                    "category": name,
                    "spent": format_brl(p.spent_cents),
                    "limit": format_brl(p.limit_cents),
                    "projected": format_brl(p.projected_cents),
                    "exceeds_on": p.exceeds_on.isoformat(),
                    "already_exceeded": already,
                },
                "title": f"Orçamento de {name} {'estourado' if already else 'em risco'}",
                "body": (
                    f"Já foram {format_brl(p.spent_cents)} de {format_brl(p.limit_cents)}."
                    if already
                    else f"No ritmo atual, {name} fecha o mês em {format_brl(p.projected_cents)} "
                    f"(limite {format_brl(p.limit_cents)}) e estoura por volta de {p.exceeds_on.strftime('%d/%m')}."
                ),
            }
        )

    # 4. end-of-month balance forecast (cash accounts)
    _, eom = month_bounds(month)
    cash = [
        a
        for a in db.exec(select(Account).where(col(Account.archived).is_(False)))
        if a.type != "credit_card"
    ]
    if cash:
        ids = {a.id for a in cash}
        balances = account_balances(db, until=on)
        current = sum(balances[a.id] for a in cash)
        future = [
            t
            for t in _txs_between(db, date.fromordinal(on.toordinal() + 1), eom)
            if t.account_id in ids
        ]
        recurring = [
            (t.date, t.amount_cents)
            for t in future
            if t.origin == "recurring" and t.type != "transfer"
        ]
        scheduled = [
            t.amount_cents for t in future if t.origin != "recurring" or t.type == "transfer"
        ]
        invoices = []
        for inv in open_invoices(db, on):
            if date.fromisoformat(inv["due_date"]) > eom:
                continue
            card = db.get(Account, inv["account_id"])
            closing = invoice_closing_date(inv["invoice_month"], card.closing_day or 1)
            paid = sum(
                t.amount_cents
                for t in _txs_between(db, closing, eom)
                if t.account_id == card.id and t.type == "transfer" and t.amount_cents > 0
            )
            invoices.append(max(0, inv["amount_cents"] - paid))
        f = forecast_balance(current, recurring, scheduled, invoices, eom)
        facts.append(
            {
                "kind": "forecast",
                "severity": "danger" if f.projected_cents < 0 else "info",
                "data": {
                    "current": format_brl(f.current_cents),
                    "recurring_in": format_brl(f.recurring_income_cents),
                    "recurring_out": format_brl(f.recurring_expense_cents),
                    "scheduled": format_brl(f.scheduled_cents),
                    "invoices_due": format_brl(f.invoices_due_cents),
                    "projected": format_brl(f.projected_cents),
                    "end_of_month": eom.isoformat(),
                },
                "title": "Previsão de saldo no fim do mês",
                "body": (
                    f"Saldo em conta hoje: {format_brl(f.current_cents)}. Com recorrentes (+{format_brl(f.recurring_income_cents)} "
                    f"/ −{format_brl(f.recurring_expense_cents)}) e faturas a vencer ({format_brl(f.invoices_due_cents)}), "
                    f"deve fechar o mês em {format_brl(f.projected_cents)}."
                ),
            }
        )
    return facts


def narrate(db: Session, facts: list[dict]) -> tuple[list[dict], dict]:
    """Ask the LLM to rewrite title/body from the computed facts. Falls back to defaults."""
    if not facts:
        return facts, {"llm": False}
    provider, model = feature_config(db, "insights")
    system, version = load_prompt("insights")
    payload = [{"kind": f["kind"], **f["data"]} for f in facts]
    try:
        res = client_for(db).call(
            "insights",
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            provider=provider,
            model=model,
            prompt_version=version,
            response_model=InsightTexts,
            temperature=0.3,
        )
    except (LLMConfigError, ProviderError, LLMValidationError) as exc:
        return facts, {"llm": False, "error": str(exc)[:200]}
    items = res.parsed.items
    if len(items) != len(facts):
        return facts, {"llm": False, "error": "a IA devolveu um número diferente de itens"}
    out = [
        {**f, "title": i.title, "body": i.body, "narrated": True}
        for f, i in zip(facts, items, strict=True)
    ]
    return out, {"llm": True, "cost_usd": res.cost_usd, "latency_ms": res.latency_ms}
