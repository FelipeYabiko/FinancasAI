"""Transaction orchestration: creation rules, installments, transfers, queries."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.domain import summary
from app.domain.dates import month_bounds
from app.domain.installments import plan_installments
from app.domain.invoices import invoice_month
from app.domain.normalize import normalize_description
from app.models import Account, Category, CategoryMemory, Transaction
from app.schemas.api import InstallmentPurchaseIn, TransactionIn, TransactionUpdate, TransferIn


class LedgerError(ValueError):
    """Business-rule violation; mapped to HTTP 400/404."""


def get_account(session: Session, account_id: int) -> Account:
    acc = session.get(Account, account_id)
    if not acc:
        raise LedgerError(f"conta {account_id} não encontrada")
    return acc


def _check_category(session: Session, category_id: int | None) -> None:
    if category_id is not None and not session.get(Category, category_id):
        raise LedgerError(f"categoria {category_id} não encontrada")


def signed_amount(amount_cents: int, tx_type: str, is_refund: bool = False) -> int:
    sign = 1 if tx_type == "income" else -1
    if is_refund and tx_type == "expense":
        sign = 1
    return sign * abs(amount_cents)


def _invoice_for(acc: Account, d: date) -> str | None:
    if acc.type == "credit_card" and acc.closing_day:
        return invoice_month(d, acc.closing_day)
    return None


def build_transaction(
    session: Session, data: TransactionIn, origin: str = "manual", **extra
) -> Transaction:
    acc = get_account(session, data.account_id)
    _check_category(session, data.category_id)
    return Transaction(
        date=data.date,
        description=data.description.strip(),
        description_normalized=normalize_description(data.description),
        amount_cents=signed_amount(data.amount_cents, data.type, data.is_refund),
        type=data.type,
        category_id=data.category_id,
        account_id=acc.id,
        invoice_month=_invoice_for(acc, data.date),
        tags=data.tags,
        notes=data.notes,
        origin=origin,
        **extra,
    )


def create_transaction(
    session: Session, data: TransactionIn, origin: str = "manual"
) -> Transaction:
    tx = build_transaction(session, data, origin)
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return tx


def update_transaction(
    session: Session, tx: Transaction, data: TransactionUpdate, learn: bool = True
) -> Transaction:
    if tx.type == "transfer":
        # Keep the pair consistent: only date/description/tags/notes are editable.
        allowed = {"date", "description", "tags", "notes"}
        changes = data.model_dump(exclude_unset=True)
        if set(changes) - allowed:
            raise LedgerError("transferências só permitem editar data, descrição, tags e notas")
        for pair in _transfer_pair(session, tx):
            for k, v in changes.items():
                if k == "description":
                    pair.description = v
                    pair.description_normalized = normalize_description(v)
                else:
                    setattr(pair, k, v)
            if "date" in changes:
                pair.invoice_month = _invoice_for(get_account(session, pair.account_id), pair.date)
            session.add(pair)
        session.commit()
        session.refresh(tx)
        return tx

    changes = data.model_dump(exclude_unset=True)
    category_changed = "category_id" in changes and changes["category_id"] != tx.category_id
    if "category_id" in changes:
        _check_category(session, changes["category_id"])
    if "account_id" in changes:
        get_account(session, changes["account_id"])
    new_type = changes.get("type", tx.type)
    magnitude = changes.get("amount_cents", abs(tx.amount_cents))
    is_refund = changes.get("is_refund", tx.type == "expense" and tx.amount_cents > 0)
    for key in ("date", "account_id", "category_id", "tags", "notes"):
        if key in changes:
            setattr(tx, key, changes[key])
    if "description" in changes:
        tx.description = changes["description"].strip()
        tx.description_normalized = normalize_description(tx.description)
    tx.type = new_type
    tx.amount_cents = signed_amount(magnitude, new_type, is_refund)
    if not tx.installment_group_id:
        tx.invoice_month = _invoice_for(get_account(session, tx.account_id), tx.date)
    session.add(tx)
    if learn and category_changed and tx.category_id is not None:
        remember_category(session, tx.description_normalized, tx.category_id)
    session.commit()
    session.refresh(tx)
    return tx


def remember_category(session: Session, normalized: str, category_id: int) -> None:
    """User corrections teach the deterministic category memory."""
    if not normalized:
        return
    mem = session.exec(
        select(CategoryMemory).where(CategoryMemory.description_normalized == normalized)
    ).first()
    if mem:
        mem.hits = mem.hits + 1 if mem.category_id == category_id else 1
        mem.category_id = category_id
    else:
        mem = CategoryMemory(description_normalized=normalized, category_id=category_id)
    session.add(mem)


def create_installment_purchase(
    session: Session, data: InstallmentPurchaseIn, origin: str = "manual"
) -> list[Transaction]:
    acc = get_account(session, data.account_id)
    _check_category(session, data.category_id)
    group = uuid.uuid4().hex
    plan = plan_installments(
        data.total_cents,
        data.installments,
        data.date,
        acc.closing_day if acc.type == "credit_card" else None,
    )
    txs = []
    for inst in plan:
        desc = f"{data.description.strip()} ({inst.number}/{inst.total})"
        tx = Transaction(
            date=inst.date,
            description=desc,
            description_normalized=normalize_description(data.description),
            amount_cents=-inst.amount_cents,
            type="expense",
            category_id=data.category_id,
            account_id=acc.id,
            invoice_month=inst.invoice_month,
            installment_group_id=group,
            installment_number=inst.number,
            installment_total=inst.total,
            tags=data.tags,
            origin=origin,
        )
        session.add(tx)
        txs.append(tx)
    session.commit()
    for tx in txs:
        session.refresh(tx)
    return txs


def create_transfer(
    session: Session, data: TransferIn, origin: str = "manual"
) -> tuple[Transaction, Transaction]:
    src = get_account(session, data.from_account_id)
    dst = get_account(session, data.to_account_id)
    pair = uuid.uuid4().hex
    common = {
        "date": data.date,
        "type": "transfer",
        "transfer_pair_id": pair,
        "origin": origin,
        "description_normalized": normalize_description(data.description),
    }
    out_tx = Transaction(
        description=f"{data.description} → {dst.name}",
        amount_cents=-data.amount_cents,
        account_id=src.id,
        invoice_month=_invoice_for(src, data.date),
        **common,
    )
    in_tx = Transaction(
        description=f"{data.description} ← {src.name}",
        amount_cents=data.amount_cents,
        account_id=dst.id,
        invoice_month=_invoice_for(dst, data.date),
        **common,
    )
    session.add(out_tx)
    session.add(in_tx)
    session.commit()
    session.refresh(out_tx)
    session.refresh(in_tx)
    return out_tx, in_tx


def _transfer_pair(session: Session, tx: Transaction) -> list[Transaction]:
    if not tx.transfer_pair_id:
        return [tx]
    return list(
        session.exec(select(Transaction).where(Transaction.transfer_pair_id == tx.transfer_pair_id))
    )


def delete_transaction(session: Session, tx: Transaction, whole_group: bool = False) -> int:
    """Delete a transaction. Transfers always delete both sides; installments
    delete the whole group when `whole_group` is set. Returns rows deleted."""
    if tx.transfer_pair_id:
        targets = _transfer_pair(session, tx)
    elif whole_group and tx.installment_group_id:
        targets = list(
            session.exec(
                select(Transaction).where(
                    Transaction.installment_group_id == tx.installment_group_id
                )
            )
        )
    else:
        targets = [tx]
    for t in targets:
        session.delete(t)
    session.commit()
    return len(targets)


@dataclass
class TxFilters:
    q: str | None = None
    category_id: int | None = None
    account_id: int | None = None
    type: str | None = None
    min_cents: int | None = None  # magnitude
    max_cents: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    month: str | None = None
    tag: str | None = None
    import_batch_id: int | None = None
    uncategorized: bool = False


def _filtered_query(f: TxFilters):
    stmt = select(Transaction)
    if f.q:
        like = f"%{f.q.strip()}%"
        norm_like = f"%{normalize_description(f.q)}%"
        stmt = stmt.where(
            or_(
                col(Transaction.description).ilike(like),
                col(Transaction.description_normalized).like(norm_like),
                col(Transaction.notes).ilike(like),
            )
        )
    if f.category_id is not None:
        stmt = stmt.where(Transaction.category_id == f.category_id)
    if f.uncategorized:
        stmt = stmt.where(col(Transaction.category_id).is_(None))
    if f.account_id is not None:
        stmt = stmt.where(Transaction.account_id == f.account_id)
    if f.type:
        stmt = stmt.where(Transaction.type == f.type)
    if f.min_cents is not None:
        stmt = stmt.where(func.abs(Transaction.amount_cents) >= f.min_cents)
    if f.max_cents is not None:
        stmt = stmt.where(func.abs(Transaction.amount_cents) <= f.max_cents)
    if f.month:
        start, end = month_bounds(f.month)
        stmt = stmt.where(Transaction.date >= start, Transaction.date <= end)
    if f.date_from:
        stmt = stmt.where(Transaction.date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Transaction.date <= f.date_to)
    if f.import_batch_id is not None:
        stmt = stmt.where(Transaction.import_batch_id == f.import_batch_id)
    return stmt


def query_transactions(
    session: Session, f: TxFilters, limit: int = 100, offset: int = 0
) -> tuple[list[Transaction], int, summary.Totals]:
    stmt = _filtered_query(f)
    rows = list(
        session.exec(stmt.order_by(col(Transaction.date).desc(), col(Transaction.id).desc()))
    )
    if f.tag:
        rows = [r for r in rows if f.tag in (r.tags or [])]
    stats = summary.totals(rows)
    return rows[offset : offset + limit], len(rows), stats


def account_balances(session: Session, until: date | None = None) -> dict[int, int]:
    stmt = select(Transaction.account_id, func.sum(Transaction.amount_cents)).group_by(
        Transaction.account_id
    )
    if until:
        stmt = stmt.where(Transaction.date <= until)
    sums = dict(session.exec(stmt).all())
    return {
        acc.id: acc.initial_balance_cents + int(sums.get(acc.id, 0) or 0)
        for acc in session.exec(select(Account))
    }
