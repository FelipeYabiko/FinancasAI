"""Assistant tools: JSON schemas, read executors and write preparation/execution.

Read tools run immediately. Write tools are only *prepared* (validated, names resolved,
human-readable summary) and become a PendingAction; they execute after user confirmation.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlmodel import Session, select

from app.domain import summary as agg
from app.domain.dates import add_months_to_month, month_bounds, month_key, today
from app.domain.installments import split_amount
from app.domain.money import format_brl
from app.domain.normalize import strip_accents
from app.models import Account, Budget, Category, Goal, Transaction
from app.schemas.api import BudgetIn, GoalIn, InstallmentPurchaseIn, TransactionIn, TransferIn
from app.services import ledger
from app.services.dashboard import budgets_for_month

READ_TOOLS = {"query_transactions", "get_summary"}
WRITE_TOOLS = {
    "create_transaction",
    "create_installment_purchase",
    "create_transfer",
    "set_budget",
    "create_goal",
    "update_goal",
    "delete_transaction",
}


class ToolError(Exception):
    """Returned to the model as a tool result so it can fix args or ask the user."""


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_DATE = {"type": "string", "description": "YYYY-MM-DD"}
_MONTH = {"type": "string", "description": "YYYY-MM"}
_CENTS = {"type": "integer", "description": "valor em centavos, positivo (R$ 45,90 = 4590)"}
_ACCOUNT = {"type": "string", "description": "nome ou id da conta"}
_CATEGORY = {"type": "string", "description": "nome ou id da categoria"}

TOOL_SPECS: list[dict] = [
    _fn(
        "query_transactions",
        "Busca transações com filtros. Devolve até `limit` itens e os totais (receitas, despesas, "
        "quantidade) de TODAS as transações que casam com o filtro.",
        {
            "text": {"type": "string", "description": "texto na descrição"},
            "category": _CATEGORY,
            "account": _ACCOUNT,
            "type": {"type": "string", "enum": ["income", "expense", "transfer"]},
            "month": _MONTH,
            "date_from": _DATE,
            "date_to": _DATE,
            "min_cents": {"type": "integer"},
            "max_cents": {"type": "integer"},
            "limit": {"type": "integer", "description": "máx. 50 (padrão 20)"},
        },
        [],
    ),
    _fn(
        "get_summary",
        "Resumo de um mês: receitas, despesas, saldo do mês, gastos por categoria, orçamentos e "
        "comparação com o mês anterior. Opcionalmente restrito a uma categoria ou conta.",
        {"month": _MONTH, "category": _CATEGORY, "account": _ACCOUNT},
        [],
    ),
    _fn(
        "create_transaction",
        "Propõe lançar uma receita ou despesa (precisa de confirmação do usuário).",
        {
            "date": _DATE,
            "description": {"type": "string"},
            "amount_cents": _CENTS,
            "type": {"type": "string", "enum": ["income", "expense"]},
            "account": _ACCOUNT,
            "category": _CATEGORY,
        },
        ["date", "description", "amount_cents", "type", "account"],
    ),
    _fn(
        "create_installment_purchase",
        "Propõe uma compra parcelada: gera uma transação por parcela em faturas consecutivas.",
        {
            "date": _DATE,
            "description": {"type": "string"},
            "total_cents": {"type": "integer", "description": "valor TOTAL da compra em centavos"},
            "installments": {"type": "integer", "description": "número de parcelas (2 a 72)"},
            "account": _ACCOUNT,
            "category": _CATEGORY,
        },
        ["date", "description", "total_cents", "installments", "account"],
    ),
    _fn(
        "create_transfer",
        "Propõe uma transferência entre contas do usuário (ex.: pagar a fatura do cartão).",
        {
            "date": _DATE,
            "from_account": _ACCOUNT,
            "to_account": _ACCOUNT,
            "amount_cents": _CENTS,
            "description": {"type": "string"},
        },
        ["date", "from_account", "to_account", "amount_cents"],
    ),
    _fn(
        "set_budget",
        "Propõe definir (criar ou alterar) o orçamento de uma categoria de despesa em um mês.",
        {"category": _CATEGORY, "month": _MONTH, "limit_cents": _CENTS},
        ["category", "month", "limit_cents"],
    ),
    _fn(
        "create_goal",
        "Propõe criar uma meta financeira.",
        {
            "name": {"type": "string"},
            "target_cents": _CENTS,
            "current_cents": {"type": "integer", "description": "já guardado, em centavos"},
            "deadline": _DATE,
        },
        ["name", "target_cents"],
    ),
    _fn(
        "update_goal",
        "Propõe atualizar o valor guardado de uma meta: `add_cents` soma (negativo retira) ou "
        "`current_cents` define o valor.",
        {
            "goal": {"type": "string", "description": "nome ou id da meta"},
            "add_cents": {"type": "integer"},
            "current_cents": {"type": "integer"},
        },
        ["goal"],
    ),
    _fn(
        "delete_transaction",
        "Propõe apagar uma transação pelo id (encontre-a antes com query_transactions).",
        {
            "transaction_id": {"type": "integer"},
            "whole_group": {
                "type": "boolean",
                "description": "se for parcela, apagar todas as parcelas da compra",
            },
        },
        ["transaction_id"],
    ),
]


# ---------------------------------------------------------------- resolution helpers
def _norm(s: str) -> str:
    return strip_accents(str(s)).lower().strip()


def _resolve(rows: list, value: Any, what: str, label=lambda r: r.name):
    if value is None or value == "":
        return None
    sval = str(value).strip()
    if sval.isdigit():
        hit = next((r for r in rows if r.id == int(sval)), None)
        if hit:
            return hit
    key = _norm(sval)
    exact = [r for r in rows if _norm(label(r)) == key]
    if len(exact) == 1:
        return exact[0]
    partial = [r for r in rows if key in _norm(label(r)) or _norm(label(r)) in key]
    if len(partial) == 1:
        return partial[0]
    options = ", ".join(label(r) for r in (partial or rows))
    if partial:
        raise ToolError(f"{what} '{value}' é ambíguo(a). Opções: {options}. Pergunte ao usuário.")
    raise ToolError(f"{what} '{value}' não encontrado(a). Existentes: {options}.")


def resolve_account(db: Session, value: Any) -> Account | None:
    rows = list(db.exec(select(Account).where(Account.archived == False)))  # noqa: E712
    return _resolve(rows, value, "conta")


def resolve_category(db: Session, value: Any, kind: str | None = None) -> Category | None:
    rows = list(db.exec(select(Category)))
    if kind:
        rows = [c for c in rows if c.kind == kind] or rows
    return _resolve(rows, value, "categoria")


def _date(value: Any, field: str = "date") -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ToolError(f"{field} inválida: '{value}' (use YYYY-MM-DD)") from exc


def _month(value: Any) -> str:
    s = str(value or "")
    try:
        month_bounds(s)
    except Exception as exc:
        raise ToolError(f"mês inválido: '{value}' (use YYYY-MM)") from exc
    return s


def _cents(value: Any, field: str) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{field} deve ser inteiro em centavos") from exc
    if v <= 0:
        raise ToolError(f"{field} deve ser positivo")
    return v


def _cat_name(db: Session, cid: int | None) -> str:
    c = db.get(Category, cid) if cid else None
    return c.name if c else "Sem categoria"


# ---------------------------------------------------------------- read tools
def query_transactions(db: Session, args: dict) -> dict:
    f = ledger.TxFilters(q=args.get("text") or None, type=args.get("type") or None)
    if args.get("category"):
        f.category_id = resolve_category(db, args["category"]).id
    if args.get("account"):
        f.account_id = resolve_account(db, args["account"]).id
    if args.get("month"):
        f.month = _month(args["month"])
    if args.get("date_from"):
        f.date_from = _date(args["date_from"], "date_from")
    if args.get("date_to"):
        f.date_to = _date(args["date_to"], "date_to")
    if args.get("min_cents") is not None:
        f.min_cents = int(args["min_cents"])
    if args.get("max_cents") is not None:
        f.max_cents = int(args["max_cents"])
    limit = max(1, min(int(args.get("limit") or 20), 50))
    items, total, stats = ledger.query_transactions(db, f, limit=limit)
    accounts = {a.id: a.name for a in db.exec(select(Account))}
    return {
        "total_matching": total,
        "returned": len(items),
        "income_cents": stats.income_cents,
        "expense_cents": stats.expense_cents,
        "income_brl": format_brl(stats.income_cents),
        "expense_brl": format_brl(stats.expense_cents),
        "transactions": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "description": t.description,
                "amount_cents": t.amount_cents,
                "amount_brl": format_brl(t.amount_cents),
                "type": t.type,
                "category": _cat_name(db, t.category_id),
                "account": accounts.get(t.account_id),
                **(
                    {"installment": f"{t.installment_number}/{t.installment_total}"}
                    if t.installment_total
                    else {}
                ),
            }
            for t in items
        ],
    }


def get_summary(db: Session, args: dict) -> dict:
    month = _month(args.get("month") or month_key(today()))
    start, end = month_bounds(month)
    stmt = select(Transaction).where(Transaction.date >= start, Transaction.date <= end)
    scope = {}
    if args.get("category"):
        cat = resolve_category(db, args["category"])
        stmt = stmt.where(Transaction.category_id == cat.id)
        scope["category"] = cat.name
    if args.get("account"):
        acc = resolve_account(db, args["account"])
        stmt = stmt.where(Transaction.account_id == acc.id)
        scope["account"] = acc.name
    txs = list(db.exec(stmt))
    t = agg.totals(txs)
    pstart, pend = month_bounds(add_months_to_month(month, -1))
    prev_stmt = select(Transaction).where(Transaction.date >= pstart, Transaction.date <= pend)
    if "category" in scope:
        prev_stmt = prev_stmt.where(Transaction.category_id == cat.id)
    if "account" in scope:
        prev_stmt = prev_stmt.where(Transaction.account_id == acc.id)
    p = agg.totals(db.exec(prev_stmt))
    by_cat = sorted(agg.expenses_by_category(txs).items(), key=lambda kv: kv[1], reverse=True)
    return {
        "month": month,
        **scope,
        "income_cents": t.income_cents,
        "expense_cents": t.expense_cents,
        "net_cents": t.net_cents,
        "income_brl": format_brl(t.income_cents),
        "expense_brl": format_brl(t.expense_cents),
        "net_brl": format_brl(t.net_cents),
        "transactions_count": t.count,
        "previous_month_expense_cents": p.expense_cents,
        "expense_change_pct": agg.pct_change(t.expense_cents, p.expense_cents),
        "expenses_by_category": [
            {"category": _cat_name(db, cid), "amount_cents": v, "amount_brl": format_brl(v)}
            for cid, v in by_cat
            if v
        ],
        "budgets": [
            {
                "category": _cat_name(db, b["category_id"]),
                "limit_brl": format_brl(b["limit_cents"]),
                "spent_brl": format_brl(b["spent_cents"]),
                "percent": b["percent"],
                "status": b["status"],
            }
            for b in budgets_for_month(db, month)
        ],
    }


def run_read_tool(db: Session, name: str, args: dict) -> dict:
    if name == "query_transactions":
        return query_transactions(db, args)
    if name == "get_summary":
        return get_summary(db, args)
    raise ToolError(f"ferramenta desconhecida: {name}")


# ---------------------------------------------------------------- write tools
@dataclass
class Prepared:
    tool: str
    arguments: dict  # normalized: ids resolved, ready for execute_write
    summary: str


def _account_or_ask(db: Session, value: Any, prefer_card: bool = False) -> Account:
    if value:
        return resolve_account(db, value)
    accounts = list(db.exec(select(Account).where(Account.archived == False)))  # noqa: E712
    if prefer_card:
        cards = [a for a in accounts if a.type == "credit_card"]
        if len(cards) == 1:
            return cards[0]
    if len(accounts) == 1:
        return accounts[0]
    raise ToolError(
        "conta não informada e há mais de uma conta. Pergunte ao usuário qual conta usar."
    )


def prepare_write(db: Session, name: str, args: dict) -> Prepared:
    try:
        return _prepare(db, name, args)
    except ValidationError as exc:
        msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
        raise ToolError(f"argumentos inválidos: {msg}") from exc


def _prepare(db: Session, name: str, args: dict) -> Prepared:
    if name == "create_transaction":
        tx_type = args.get("type") or "expense"
        if tx_type not in ("income", "expense"):
            raise ToolError("type deve ser income ou expense")
        acc = _account_or_ask(db, args.get("account"))
        cat = resolve_category(db, args.get("category"), kind=tx_type)
        data = TransactionIn(
            date=_date(args.get("date")),
            description=str(args.get("description") or "").strip() or "Lançamento",
            amount_cents=_cents(args.get("amount_cents"), "amount_cents"),
            type=tx_type,
            account_id=acc.id,
            category_id=cat.id if cat else None,
        )
        verb = "Receita" if tx_type == "income" else "Despesa"
        summary = (
            f"{verb} de {format_brl(data.amount_cents)} — “{data.description}” em "
            f"{data.date.strftime('%d/%m/%Y')}, conta {acc.name}, categoria {_cat_name(db, data.category_id)}"
        )
        return Prepared(name, data.model_dump(mode="json"), summary)

    if name == "create_installment_purchase":
        acc = _account_or_ask(db, args.get("account"), prefer_card=True)
        cat = resolve_category(db, args.get("category"), kind="expense")
        data = InstallmentPurchaseIn(
            date=_date(args.get("date")),
            description=str(args.get("description") or "").strip() or "Compra parcelada",
            total_cents=_cents(args.get("total_cents"), "total_cents"),
            installments=int(args.get("installments") or 0),
            account_id=acc.id,
            category_id=cat.id if cat else None,
        )
        parts = split_amount(data.total_cents, data.installments)
        summary = (
            f"Compra parcelada “{data.description}”: {format_brl(data.total_cents)} em "
            f"{data.installments}x de {format_brl(parts[0])}"
            f"{f' (última {format_brl(parts[-1])})' if parts[-1] != parts[0] else ''}"
            f" na conta {acc.name}, a partir de {data.date.strftime('%d/%m/%Y')}"
        )
        return Prepared(name, data.model_dump(mode="json"), summary)

    if name == "create_transfer":
        src = resolve_account(db, args.get("from_account"))
        dst = resolve_account(db, args.get("to_account"))
        if not src or not dst:
            raise ToolError("informe a conta de origem e a de destino")
        data = TransferIn(
            date=_date(args.get("date")),
            from_account_id=src.id,
            to_account_id=dst.id,
            amount_cents=_cents(args.get("amount_cents"), "amount_cents"),
            description=str(args.get("description") or "Transferência"),
        )
        summary = (
            f"Transferência de {format_brl(data.amount_cents)} de {src.name} para {dst.name} em "
            f"{data.date.strftime('%d/%m/%Y')}"
        )
        return Prepared(name, data.model_dump(mode="json"), summary)

    if name == "set_budget":
        cat = resolve_category(db, args.get("category"), kind="expense")
        if not cat:
            raise ToolError("informe a categoria do orçamento")
        data = BudgetIn(
            category_id=cat.id,
            month=_month(args.get("month") or month_key(today())),
            limit_cents=_cents(args.get("limit_cents"), "limit_cents"),
        )
        existing = db.exec(
            select(Budget).where(Budget.category_id == cat.id, Budget.month == data.month)
        ).first()
        action = (
            f"Alterar orçamento (era {format_brl(existing.limit_cents)})"
            if existing
            else "Criar orçamento"
        )
        summary = f"{action} de {cat.name} em {data.month}: {format_brl(data.limit_cents)}"
        return Prepared(name, data.model_dump(mode="json"), summary)

    if name == "create_goal":
        data = GoalIn(
            name=str(args.get("name") or "").strip(),
            target_cents=_cents(args.get("target_cents"), "target_cents"),
            current_cents=int(args.get("current_cents") or 0),
            deadline=_date(args["deadline"], "deadline") if args.get("deadline") else None,
        )
        summary = f"Criar meta “{data.name}” de {format_brl(data.target_cents)}"
        if data.current_cents:
            summary += f", já com {format_brl(data.current_cents)}"
        if data.deadline:
            summary += f", até {data.deadline.strftime('%d/%m/%Y')}"
        return Prepared(name, data.model_dump(mode="json"), summary)

    if name == "update_goal":
        goals = list(db.exec(select(Goal)))
        goal = _resolve(goals, args.get("goal"), "meta")
        if not goal:
            raise ToolError("informe qual meta atualizar")
        if args.get("current_cents") is not None:
            new = int(args["current_cents"])
        elif args.get("add_cents") is not None:
            new = goal.current_cents + int(args["add_cents"])
        else:
            raise ToolError("informe add_cents ou current_cents")
        if new < 0:
            raise ToolError("o valor da meta não pode ficar negativo")
        summary = (
            f"Meta “{goal.name}”: {format_brl(goal.current_cents)} → {format_brl(new)} "
            f"de {format_brl(goal.target_cents)}"
        )
        return Prepared(name, {"goal_id": goal.id, "current_cents": new}, summary)

    if name == "delete_transaction":
        try:
            tx = db.get(Transaction, int(args.get("transaction_id")))
        except (TypeError, ValueError):
            tx = None
        if not tx:
            raise ToolError("transação não encontrada; use query_transactions para achar o id")
        whole = bool(args.get("whole_group")) and bool(tx.installment_group_id)
        what = (
            f"todas as {tx.installment_total} parcelas de “{tx.description}”"
            if whole
            else f"“{tx.description}” de {format_brl(tx.amount_cents)} em {tx.date.strftime('%d/%m/%Y')}"
        )
        if tx.transfer_pair_id:
            what += " (e o outro lado da transferência)"
        return Prepared(name, {"transaction_id": tx.id, "whole_group": whole}, f"Apagar {what}")

    raise ToolError(f"ferramenta desconhecida: {name}")


def execute_write(db: Session, tool: str, args: dict) -> dict:
    """Run a confirmed action. Arguments come from `prepare_write` (already normalized)."""
    if tool == "create_transaction":
        tx = ledger.create_transaction(db, TransactionIn(**args), origin="assistant")
        return {"transaction_ids": [tx.id], "month": month_key(tx.date)}
    if tool == "create_installment_purchase":
        txs = ledger.create_installment_purchase(
            db, InstallmentPurchaseIn(**args), origin="assistant"
        )
        return {"transaction_ids": [t.id for t in txs], "month": month_key(txs[0].date)}
    if tool == "create_transfer":
        pair = ledger.create_transfer(db, TransferIn(**args), origin="assistant")
        return {"transaction_ids": [t.id for t in pair], "month": month_key(pair[0].date)}
    if tool == "set_budget":
        from app.api.planning import upsert_budget

        b = upsert_budget(db, BudgetIn(**args))
        return {"budget_id": b.id}
    if tool == "create_goal":
        g = Goal(**GoalIn(**args).model_dump())
        db.add(g)
        db.commit()
        db.refresh(g)
        return {"goal_id": g.id}
    if tool == "update_goal":
        g = db.get(Goal, args["goal_id"])
        if not g:
            raise ToolError("meta não existe mais")
        g.current_cents = args["current_cents"]
        db.add(g)
        db.commit()
        return {"goal_id": g.id, "current_cents": g.current_cents}
    if tool == "delete_transaction":
        tx = db.get(Transaction, args["transaction_id"])
        if not tx:
            raise ToolError("transação não existe mais")
        n = ledger.delete_transaction(db, tx, whole_group=args.get("whole_group", False))
        return {"deleted": n}
    raise ToolError(f"ferramenta desconhecida: {tool}")
