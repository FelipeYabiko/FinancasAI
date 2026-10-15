from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from app.api.deps import current_auth
from app.db import get_session
from app.models import Account, Budget, Category, CategoryMemory, RecurringRule, Transaction
from app.schemas.api import AccountIn, AccountOut, CategoryIn, CategoryMemoryOut, CategoryOut
from app.services.ledger import account_balances

router = APIRouter(prefix="/api", tags=["accounts"], dependencies=[Depends(current_auth)])


def _account_out(acc: Account, balances: dict[int, int]) -> AccountOut:
    return AccountOut(
        **acc.model_dump(), balance_cents=balances.get(acc.id, acc.initial_balance_cents)
    )


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_session)):
    from app.domain.dates import today

    balances = account_balances(db, until=today())
    return [_account_out(a, balances) for a in db.exec(select(Account).order_by(Account.id))]


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(data: AccountIn, db: Session = Depends(get_session)):
    acc = Account(**data.model_dump())
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return _account_out(acc, {})


@router.put("/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: int, data: AccountIn, db: Session = Depends(get_session)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="conta não encontrada")
    if (
        acc.type != data.type
        and db.exec(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id)
        ).one()
    ):
        raise HTTPException(
            status_code=400, detail="não é possível mudar o tipo de uma conta com transações"
        )
    for k, v in data.model_dump().items():
        setattr(acc, k, v)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return _account_out(acc, account_balances(db))


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_session)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="conta não encontrada")
    used = (
        db.exec(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id)
        ).one()
        + db.exec(
            select(func.count())
            .select_from(RecurringRule)
            .where(RecurringRule.account_id == account_id)
        ).one()
    )
    if used:
        raise HTTPException(
            status_code=400,
            detail="a conta tem transações ou recorrências; arquive-a em vez de excluir",
        )
    db.delete(acc)
    db.commit()
    return {"ok": True}


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_session)):
    return db.exec(select(Category).order_by(Category.kind, Category.name)).all()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, db: Session = Depends(get_session)):
    cat = Category(**data.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryIn, db: Session = Depends(get_session)):
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="categoria não encontrada")
    for k, v in data.model_dump().items():
        setattr(cat, k, v)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_session)):
    """Delete a category; its transactions become uncategorized."""
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="categoria não encontrada")
    for tx in db.exec(select(Transaction).where(Transaction.category_id == category_id)):
        tx.category_id = None
        db.add(tx)
    for rule in db.exec(select(RecurringRule).where(RecurringRule.category_id == category_id)):
        rule.category_id = None
        db.add(rule)
    for model in (Budget, CategoryMemory):
        for row in db.exec(select(model).where(model.category_id == category_id)):
            db.delete(row)
    db.flush()
    db.delete(cat)
    db.commit()
    return {"ok": True}


@router.get("/category-memory", response_model=list[CategoryMemoryOut])
def list_memory(db: Session = Depends(get_session)):
    return db.exec(select(CategoryMemory).order_by(CategoryMemory.description_normalized)).all()


@router.delete("/category-memory/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_session)):
    mem = db.get(CategoryMemory, memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="não encontrado")
    db.delete(mem)
    db.commit()
    return {"ok": True}
