"""Request/response schemas for the HTTP API."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AccountType = Literal["checking", "credit_card", "cash", "savings"]
CategoryKind = Literal["income", "expense"]
TxType = Literal["income", "expense", "transfer"]
MonthStr = str  # 'YYYY-MM'

_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


# ---------- Auth ----------
class LoginIn(BaseModel):
    username: str
    password: str


class SetupIn(BaseModel):
    name: str = Field(min_length=1)
    username: str = Field(min_length=2)
    password: str = Field(min_length=6)


class UserOut(BaseModel):
    id: int
    name: str
    username: str


class UserCreate(SetupIn):
    pass


# ---------- Accounts ----------
class AccountIn(BaseModel):
    name: str = Field(min_length=1)
    type: AccountType
    initial_balance_cents: int = 0
    closing_day: int | None = Field(default=None, ge=1, le=31)
    due_day: int | None = Field(default=None, ge=1, le=31)
    color: str = "#4f46e5"
    archived: bool = False

    @model_validator(mode="after")
    def _card_days(self):
        if self.type == "credit_card" and (self.closing_day is None or self.due_day is None):
            raise ValueError("credit_card accounts need closing_day and due_day")
        if self.type != "credit_card":
            self.closing_day = None
            self.due_day = None
        return self


class AccountOut(AccountIn):
    id: int
    balance_cents: int = 0


# ---------- Categories ----------
class CategoryIn(BaseModel):
    name: str = Field(min_length=1)
    kind: CategoryKind
    icon: str = "🏷️"
    color: str = "#64748b"


class CategoryOut(CategoryIn):
    id: int


# ---------- Transactions ----------
class TransactionIn(BaseModel):
    """Create a single income/expense. `amount_cents` is the positive magnitude;
    the stored sign comes from `type` (`is_refund` flips it for expenses)."""

    date: dt.date
    description: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)
    type: Literal["income", "expense"]
    account_id: int
    category_id: int | None = None
    tags: list[str] = []
    notes: str = ""
    is_refund: bool = False


class TransactionUpdate(BaseModel):
    date: dt.date | None = None
    description: str | None = None
    amount_cents: int | None = Field(default=None, gt=0)
    type: Literal["income", "expense"] | None = None
    account_id: int | None = None
    category_id: int | None = None
    tags: list[str] | None = None
    notes: str | None = None
    is_refund: bool | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    description: str
    description_normalized: str
    amount_cents: int
    type: TxType
    category_id: int | None
    account_id: int
    invoice_month: str | None
    installment_group_id: str | None
    installment_number: int | None
    installment_total: int | None
    transfer_pair_id: str | None
    tags: list[str]
    origin: str
    import_batch_id: int | None
    notes: str


class InstallmentPurchaseIn(BaseModel):
    date: dt.date
    description: str = Field(min_length=1)
    total_cents: int = Field(gt=0)
    installments: int = Field(ge=2, le=72)
    account_id: int
    category_id: int | None = None
    tags: list[str] = []


class TransferIn(BaseModel):
    date: dt.date
    from_account_id: int
    to_account_id: int
    amount_cents: int = Field(gt=0)
    description: str = "Transferência"

    @model_validator(mode="after")
    def _different(self):
        if self.from_account_id == self.to_account_id:
            raise ValueError("from_account_id and to_account_id must differ")
        return self


class TxStats(BaseModel):
    count: int
    income_cents: int
    expense_cents: int
    net_cents: int


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    stats: TxStats


# ---------- Budgets / goals / recurring ----------
class BudgetIn(BaseModel):
    category_id: int
    month: str = Field(pattern=_MONTH_PATTERN)
    limit_cents: int = Field(gt=0)


class BudgetOut(BudgetIn):
    id: int
    spent_cents: int = 0
    percent: float = 0.0
    status: Literal["ok", "warning", "exceeded"] = "ok"


class GoalIn(BaseModel):
    name: str = Field(min_length=1)
    target_cents: int = Field(gt=0)
    current_cents: int = Field(default=0, ge=0)
    deadline: dt.date | None = None


class GoalUpdate(BaseModel):
    name: str | None = None
    target_cents: int | None = Field(default=None, gt=0)
    current_cents: int | None = Field(default=None, ge=0)
    deadline: dt.date | None = None


class GoalOut(GoalIn):
    id: int
    percent: float = 0.0


class RecurringIn(BaseModel):
    description: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)
    type: Literal["income", "expense"]
    category_id: int | None = None
    account_id: int
    day_of_month: int = Field(ge=1, le=31)
    start_month: str = Field(pattern=_MONTH_PATTERN)
    active: bool = True


class RecurringOut(RecurringIn):
    id: int


# ---------- Category memory ----------
class CategoryMemoryOut(BaseModel):
    id: int
    description_normalized: str
    category_id: int
    hits: int


# ---------- Settings ----------
class FeatureModel(BaseModel):
    provider: str
    model: str


class AISettings(BaseModel):
    extraction: FeatureModel
    categorization: FeatureModel
    assistant: FeatureModel
    insights: FeatureModel

    @field_validator("*")
    @classmethod
    def _non_empty(cls, v: FeatureModel) -> FeatureModel:
        if not v.provider or not v.model:
            raise ValueError("provider and model are required")
        return v
