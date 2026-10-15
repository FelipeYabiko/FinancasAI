import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class PreviewRow(BaseModel):
    row_id: int
    date: dt.date
    description: str
    amount_cents: int
    type: Literal["income", "expense", "transfer"]
    confidence: float
    low_confidence: bool = False
    installment_number: int | None = None
    installment_total: int | None = None
    category_id: int | None = None
    suggested_category_id: int | None = None
    category_source: str = "none"
    duplicate: Literal["db", "file", "near"] | None = None
    duplicate_of: int | None = None
    dedup_hash: str | None = None
    selected: bool = True


class CommitRow(BaseModel):
    date: dt.date
    description: str = Field(min_length=1, max_length=300)
    amount_cents: int
    type: Literal["income", "expense", "transfer"]
    installment_number: int | None = None
    installment_total: int | None = None
    category_id: int | None = None
    suggested_category_id: int | None = None
    selected: bool = True
    force: bool = False  # import even if an identical transaction exists


class CommitIn(BaseModel):
    rows: list[CommitRow]
    invoice_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
