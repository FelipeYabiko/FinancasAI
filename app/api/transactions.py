from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.deps import current_auth
from app.db import get_session
from app.models import Transaction
from app.schemas.api import (
    InstallmentPurchaseIn,
    TransactionIn,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
    TransferIn,
    TxStats,
)
from app.services import ledger

router = APIRouter(
    prefix="/api/transactions", tags=["transactions"], dependencies=[Depends(current_auth)]
)


def _get(db: Session, tx_id: int) -> Transaction:
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="transação não encontrada")
    return tx


@router.get("", response_model=TransactionPage)
def list_transactions(
    q: str | None = None,
    category_id: int | None = None,
    uncategorized: bool = False,
    account_id: int | None = None,
    type: str | None = None,
    min_cents: int | None = None,
    max_cents: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    tag: str | None = None,
    import_batch_id: int | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_session),
):
    f = ledger.TxFilters(
        q=q,
        category_id=category_id,
        uncategorized=uncategorized,
        account_id=account_id,
        type=type,
        min_cents=min_cents,
        max_cents=max_cents,
        date_from=date_from,
        date_to=date_to,
        month=month,
        tag=tag,
        import_batch_id=import_batch_id,
    )
    items, total, stats = ledger.query_transactions(db, f, limit, offset)
    return TransactionPage(
        items=items,
        total=total,
        stats=TxStats(
            count=stats.count,
            income_cents=stats.income_cents,
            expense_cents=stats.expense_cents,
            net_cents=stats.net_cents,
        ),
    )


@router.post("", response_model=TransactionOut, status_code=201)
def create(data: TransactionIn, db: Session = Depends(get_session)):
    return ledger.create_transaction(db, data)


@router.post("/installments", response_model=list[TransactionOut], status_code=201)
def create_installments(data: InstallmentPurchaseIn, db: Session = Depends(get_session)):
    return ledger.create_installment_purchase(db, data)


@router.post("/transfers", response_model=list[TransactionOut], status_code=201)
def create_transfer(data: TransferIn, db: Session = Depends(get_session)):
    return list(ledger.create_transfer(db, data))


@router.get("/{tx_id}", response_model=TransactionOut)
def get_one(tx_id: int, db: Session = Depends(get_session)):
    return _get(db, tx_id)


@router.patch("/{tx_id}", response_model=TransactionOut)
def update(tx_id: int, data: TransactionUpdate, db: Session = Depends(get_session)):
    return ledger.update_transaction(db, _get(db, tx_id), data)


@router.delete("/{tx_id}")
def delete(tx_id: int, whole_group: bool = False, db: Session = Depends(get_session)) -> dict:
    deleted = ledger.delete_transaction(db, _get(db, tx_id), whole_group=whole_group)
    return {"deleted": deleted}
