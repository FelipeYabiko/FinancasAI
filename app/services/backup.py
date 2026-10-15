"""JSON backup/restore and CSV export."""

import csv
import io
from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, delete, select

from app.domain.money import cents_to_decimal
from app.models import (
    Account,
    Budget,
    Category,
    CategoryMemory,
    Goal,
    ImportBatch,
    RecurringRule,
    Transaction,
)
from app.services.ledger import LedgerError

BACKUP_VERSION = 1
# Insertion order respects foreign keys; deletion uses the reverse.
TABLES: list[tuple[str, type[SQLModel]]] = [
    ("categories", Category),
    ("accounts", Account),
    ("goals", Goal),
    ("import_batches", ImportBatch),
    ("recurring_rules", RecurringRule),
    ("category_memory", CategoryMemory),
    ("budgets", Budget),
    ("transactions", Transaction),
]


def export_json(session: Session) -> dict:
    data: dict = {
        "app": "financasia",
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
    }
    for key, model in TABLES:
        data[key] = [row.model_dump(mode="json") for row in session.exec(select(model))]
    return data


def import_json(session: Session, data: dict) -> dict[str, int]:
    """Replace all household data with the backup content (atomic)."""
    if data.get("app") != "financasia" or data.get("version") != BACKUP_VERSION:
        raise LedgerError("arquivo de backup inválido ou de versão incompatível")
    parsed: dict[str, list[SQLModel]] = {}
    for key, model in TABLES:
        try:
            parsed[key] = [model.model_validate(row) for row in data.get(key, [])]
        except Exception as exc:
            raise LedgerError(f"backup inválido em '{key}': {exc}") from exc
    try:
        for _, model in reversed(TABLES):
            session.exec(delete(model))
        for key, _ in TABLES:
            session.add_all(parsed[key])
            session.flush()
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {key: len(rows) for key, rows in parsed.items()}


CSV_COLUMNS = [
    "id",
    "date",
    "description",
    "amount",
    "type",
    "category",
    "account",
    "invoice_month",
    "installment",
    "tags",
    "origin",
]


def export_csv(session: Session) -> str:
    cats = {c.id: c.name for c in session.exec(select(Category))}
    accs = {a.id: a.name for a in session.exec(select(Account))}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(CSV_COLUMNS)
    for tx in session.exec(select(Transaction).order_by(Transaction.date)):
        w.writerow(
            [
                tx.id,
                tx.date.isoformat(),
                tx.description,
                cents_to_decimal(tx.amount_cents),
                tx.type,
                cats.get(tx.category_id, ""),
                accs.get(tx.account_id, ""),
                tx.invoice_month or "",
                f"{tx.installment_number}/{tx.installment_total}" if tx.installment_total else "",
                ",".join(tx.tags or []),
                tx.origin,
            ]
        )
    return buf.getvalue()
