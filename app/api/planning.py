"""Budgets, goals and recurring rules."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import current_auth
from app.db import get_session
from app.domain.dates import month_key, today
from app.models import Account, Budget, Category, Goal, RecurringRule
from app.schemas.api import (
    BudgetIn,
    BudgetOut,
    GoalIn,
    GoalOut,
    GoalUpdate,
    RecurringIn,
    RecurringOut,
)
from app.services.dashboard import budgets_for_month
from app.services.recurring import run_recurring

router = APIRouter(prefix="/api", tags=["planning"], dependencies=[Depends(current_auth)])


def _404(what: str):
    return HTTPException(status_code=404, detail=f"{what} não encontrado(a)")


# ---- budgets ----
@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(month: str | None = None, db: Session = Depends(get_session)):
    return budgets_for_month(db, month or month_key(today()))


def upsert_budget(db: Session, data: BudgetIn) -> Budget:
    if not db.get(Category, data.category_id):
        raise _404("categoria")
    b = db.exec(
        select(Budget).where(Budget.category_id == data.category_id, Budget.month == data.month)
    ).first()
    if b:
        b.limit_cents = data.limit_cents
    else:
        b = Budget(**data.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.put("/budgets", response_model=BudgetOut)
def set_budget(data: BudgetIn, db: Session = Depends(get_session)):
    b = upsert_budget(db, data)
    return next(x for x in budgets_for_month(db, b.month) if x["id"] == b.id)


@router.post("/budgets/copy")
def copy_budgets(from_month: str, to_month: str, db: Session = Depends(get_session)) -> dict:
    """Copy every budget from one month to another (existing ones are kept)."""
    existing = {b.category_id for b in db.exec(select(Budget).where(Budget.month == to_month))}
    n = 0
    for b in db.exec(select(Budget).where(Budget.month == from_month)):
        if b.category_id not in existing:
            db.add(Budget(category_id=b.category_id, month=to_month, limit_cents=b.limit_cents))
            n += 1
    db.commit()
    return {"copied": n}


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, db: Session = Depends(get_session)):
    b = db.get(Budget, budget_id)
    if not b:
        raise _404("orçamento")
    db.delete(b)
    db.commit()
    return {"ok": True}


# ---- goals ----
def _goal_out(g: Goal) -> GoalOut:
    pct = round(min(g.current_cents / g.target_cents * 100, 100), 1) if g.target_cents else 0.0
    return GoalOut(**g.model_dump(), percent=pct)


@router.get("/goals", response_model=list[GoalOut])
def list_goals(db: Session = Depends(get_session)):
    return [_goal_out(g) for g in db.exec(select(Goal).order_by(Goal.id))]


@router.post("/goals", response_model=GoalOut, status_code=201)
def create_goal(data: GoalIn, db: Session = Depends(get_session)):
    g = Goal(**data.model_dump())
    db.add(g)
    db.commit()
    db.refresh(g)
    return _goal_out(g)


@router.patch("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, data: GoalUpdate, db: Session = Depends(get_session)):
    g = db.get(Goal, goal_id)
    if not g:
        raise _404("meta")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    db.add(g)
    db.commit()
    db.refresh(g)
    return _goal_out(g)


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_session)):
    g = db.get(Goal, goal_id)
    if not g:
        raise _404("meta")
    db.delete(g)
    db.commit()
    return {"ok": True}


# ---- recurring ----
def _validate_rule(db: Session, data: RecurringIn) -> None:
    if not db.get(Account, data.account_id):
        raise _404("conta")
    if data.category_id is not None and not db.get(Category, data.category_id):
        raise _404("categoria")


@router.get("/recurring", response_model=list[RecurringOut])
def list_recurring(db: Session = Depends(get_session)):
    return db.exec(select(RecurringRule).order_by(RecurringRule.day_of_month)).all()


@router.post("/recurring", response_model=RecurringOut, status_code=201)
def create_recurring(data: RecurringIn, db: Session = Depends(get_session)):
    _validate_rule(db, data)
    rule = RecurringRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    run_recurring(db)
    return rule


@router.put("/recurring/{rule_id}", response_model=RecurringOut)
def update_recurring(rule_id: int, data: RecurringIn, db: Session = Depends(get_session)):
    rule = db.get(RecurringRule, rule_id)
    if not rule:
        raise _404("recorrência")
    _validate_rule(db, data)
    for k, v in data.model_dump().items():
        setattr(rule, k, v)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    run_recurring(db)
    return rule


@router.delete("/recurring/{rule_id}")
def delete_recurring(rule_id: int, db: Session = Depends(get_session)):
    """Delete the rule; transactions already generated are kept."""
    rule = db.get(RecurringRule, rule_id)
    if not rule:
        raise _404("recorrência")
    from app.models import Transaction

    for tx in db.exec(select(Transaction).where(Transaction.recurring_rule_id == rule_id)):
        tx.recurring_rule_id = None
        db.add(tx)
    db.flush()
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/recurring/run")
def run_now(db: Session = Depends(get_session)) -> dict:
    return {"created": len(run_recurring(db))}
