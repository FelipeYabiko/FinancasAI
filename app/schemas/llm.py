"""Schemas for structured LLM output. Validated with Pydantic; one corrective retry."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ExtractedTransaction(BaseModel):
    date: dt.date = Field(description="Data da transação no formato YYYY-MM-DD")
    description: str = Field(min_length=1, max_length=300)
    amount_cents: int = Field(description="Valor em centavos, com sinal: saída de dinheiro < 0")
    type: Literal["income", "expense", "transfer"]
    confidence: float = Field(ge=0, le=1)
    installment_number: int | None = Field(default=None, ge=1)
    installment_total: int | None = Field(default=None, ge=1)

    @field_validator("description")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("descrição vazia")
        return v

    @model_validator(mode="after")
    def _consistency(self):
        if self.amount_cents == 0:
            raise ValueError("amount_cents não pode ser zero")
        if self.type == "income" and self.amount_cents < 0:
            raise ValueError("receita (income) deve ter amount_cents positivo")
        if (self.installment_number is None) != (self.installment_total is None):
            raise ValueError("installment_number e installment_total vêm juntos")
        if self.installment_total and self.installment_number > self.installment_total:
            raise ValueError("installment_number maior que installment_total")
        return self


class ExtractionOutput(BaseModel):
    transactions: list[ExtractedTransaction]


class CategorizedItem(BaseModel):
    index: int = Field(ge=0)
    category: str


class CategorizationOutput(BaseModel):
    items: list[CategorizedItem]


class InsightText(BaseModel):
    title: str = Field(max_length=100)
    body: str = Field(max_length=500)


class InsightTexts(BaseModel):
    items: list[InsightText]
