"""SQLModel tables. Money is always integer cents."""

import datetime as dt
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    username: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow)


class UserSession(SQLModel, table=True):
    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    csrf_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    type: str  # checking | credit_card | cash | savings
    initial_balance_cents: int = 0
    closing_day: int | None = None  # credit card only
    due_day: int | None = None  # credit card only
    color: str = "#4f46e5"
    archived: bool = False


class Category(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    kind: str  # income | expense
    icon: str = "🏷️"
    color: str = "#64748b"


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    date: dt.date = Field(index=True)
    description: str
    description_normalized: str = Field(default="", index=True)
    # Signed: money in > 0, money out < 0.
    amount_cents: int
    type: str = Field(index=True)  # income | expense | transfer
    category_id: int | None = Field(default=None, foreign_key="category.id", index=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    invoice_month: str | None = Field(default=None, index=True)  # 'YYYY-MM', credit card only
    installment_group_id: str | None = Field(default=None, index=True)
    installment_number: int | None = None
    installment_total: int | None = None
    transfer_pair_id: str | None = Field(default=None, index=True)
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    origin: str = "manual"  # manual | import | assistant | recurring
    import_batch_id: int | None = Field(default=None, foreign_key="importbatch.id", index=True)
    recurring_rule_id: int | None = Field(default=None, foreign_key="recurringrule.id")
    recurring_month: str | None = None
    dedup_hash: str | None = Field(default=None, index=True)
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Budget(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("category_id", "month"),)
    id: int | None = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id")
    month: str  # 'YYYY-MM'
    limit_cents: int


class Goal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    target_cents: int
    current_cents: int = 0
    deadline: dt.date | None = None


class RecurringRule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    description: str
    amount_cents: int  # positive magnitude; sign derived from type
    type: str  # income | expense
    category_id: int | None = Field(default=None, foreign_key="category.id")
    account_id: int = Field(foreign_key="account.id")
    day_of_month: int
    start_month: str  # 'YYYY-MM'
    active: bool = True


class CategoryMemory(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    description_normalized: str = Field(unique=True, index=True)
    category_id: int = Field(foreign_key="category.id")
    hits: int = 1
    updated_at: datetime = Field(default_factory=utcnow)


class ImportBatch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str
    bank: str | None = None
    document_type: str | None = None  # checking_statement | credit_card_invoice
    account_id: int | None = Field(default=None, foreign_key="account.id")
    created_at: datetime = Field(default_factory=utcnow)
    imported_count: int = 0
    skipped_count: int = 0
    status: str = "pending"  # pending | committed | undone | failed
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


class LLMCall(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    feature: str = Field(index=True)  # extraction | categorization | assistant | insights
    prompt_version: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0  # estimate from pricing.yaml (not money we track in cents)
    latency_ms: int = 0
    status: str = "ok"  # ok | error | validation_error
    attempts: int = 1
    error_message: str | None = None
    request_payload: str | None = None  # only when LLM_LOG_PAYLOADS=true
    response_payload: str | None = None


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
