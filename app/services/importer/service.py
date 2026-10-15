"""Import orchestration: preview (steps 1-6) → user review → commit / undo."""

import uuid
from datetime import date

from sqlmodel import Session, col, select

from app.config import get_settings
from app.domain.dates import month_key
from app.domain.dedup import dedup_hash, is_near_duplicate
from app.domain.invoices import invoice_month
from app.domain.normalize import normalize_description
from app.models import Account, Category, CategoryMemory, ImportBatch, Transaction
from app.schemas.imports import CommitRow, PreviewRow
from app.services.ai_config import client_for, feature_config
from app.services.importer.categorize import CatItem, categorize
from app.services.importer.extraction import extract_transactions
from app.services.importer.pdf_text import extract_pdf_text
from app.services.ledger import LedgerError, remember_category

LOW_CONFIDENCE = 0.7
MAX_PDF_BYTES = 10 * 1024 * 1024


def _mark_duplicates(db: Session, account_id: int, rows: list[PreviewRow]) -> None:
    """Exact (dedup_hash) and near duplicates, against the DB and within the file."""
    if not rows:
        return
    lo = min(r.date for r in rows)
    hi = max(r.date for r in rows)
    existing = list(
        db.exec(
            select(Transaction).where(
                Transaction.account_id == account_id, Transaction.date >= lo, Transaction.date <= hi
            )
        )
    )
    by_hash = {t.dedup_hash: t for t in existing if t.dedup_hash}
    seen: dict[str, PreviewRow] = {}
    for r in rows:
        norm = normalize_description(r.description)
        h = dedup_hash(r.date, r.amount_cents, norm, account_id)
        r.dedup_hash = h
        if h in by_hash:
            r.duplicate = "db"
            r.duplicate_of = by_hash[h].id
        elif h in seen:
            # Same line twice in one file is usually legit (two equal purchases on the same
            # day), so it's flagged for review but stays selected.
            r.duplicate = "file"
        else:
            near = next(
                (t for t in existing if is_near_duplicate(r.date, r.amount_cents, norm, t.date, t.amount_cents,
                                                          t.description_normalized)),
                None,
            )  # fmt: skip
            if near:
                r.duplicate = "near"
                r.duplicate_of = near.id
        seen.setdefault(h, r)
        r.selected = r.duplicate in (None, "file")


def preview_import(db: Session, data: bytes, filename: str, account_id: int) -> dict:
    account = db.get(Account, account_id)
    if not account:
        raise LedgerError("conta não encontrada")
    if len(data) > MAX_PDF_BYTES:
        raise LedgerError("arquivo maior que 10 MB")
    batch = ImportBatch(filename=filename[:200], account_id=account_id, status="pending")
    db.add(batch)
    db.commit()
    db.refresh(batch)
    try:
        pdf = extract_pdf_text(data)  # in memory; the bytes are discarded after this request
        provider, model = feature_config(db, "extraction")
        client = client_for(db)
        run = extract_transactions(pdf, client, provider, model,
                                   chunk_tokens=get_settings().extraction_chunk_tokens)  # fmt: skip
    except Exception as exc:
        batch.status = "failed"
        batch.warnings = [str(exc)[:300]]
        db.add(batch)
        db.commit()
        raise
    del data, pdf

    warnings = list(run.warnings)
    info = run.info
    if info.document_type == "credit_card_invoice" and account.type != "credit_card":
        warnings.append(
            "o documento parece uma fatura de cartão, mas a conta escolhida não é um cartão"
        )
    if info.document_type == "checking_statement" and account.type == "credit_card":
        warnings.append("o documento parece um extrato de conta, mas a conta escolhida é um cartão")

    cats = list(db.exec(select(Category)))
    memory = {m.description_normalized: m.category_id for m in db.exec(select(CategoryMemory))}
    cat_provider, cat_model = feature_config(db, "categorization")
    cat_run = categorize(
        [CatItem(t.description, t.type) for t in run.transactions],
        [(c.id, c.name, c.kind) for c in cats],
        memory,
        client_for(db),
        cat_provider,
        cat_model,
    )
    warnings.extend(cat_run.warnings or [])

    rows = []
    for i, (t, c) in enumerate(zip(run.transactions, cat_run.results, strict=True)):
        rows.append(
            PreviewRow(
                row_id=i,
                date=t.date,
                description=t.description,
                amount_cents=t.amount_cents,
                type=t.type,
                confidence=t.confidence,
                low_confidence=t.confidence < LOW_CONFIDENCE,
                installment_number=t.installment_number,
                installment_total=t.installment_total,
                category_id=c.category_id,
                suggested_category_id=c.category_id,
                category_source=c.source,
            )
        )
    _mark_duplicates(db, account_id, rows)

    batch.bank = info.bank
    batch.document_type = info.document_type
    batch.warnings = warnings
    db.add(batch)
    db.commit()
    return {
        "batch_id": batch.id,
        "bank": info.bank,
        "document_type": info.document_type,
        "period_start": info.period_start,
        "period_end": info.period_end,
        "invoice_month": info.invoice_month,
        "account_id": account_id,
        "warnings": warnings,
        "rows": rows,
        "stats": {
            "chunks": run.chunks,
            "failed_chunks": run.failed_chunks,
            "llm_calls": run.llm_calls + cat_run.llm_calls,
            "validation_retries": run.validation_retries,
            "cost_usd": round(run.cost_usd + cat_run.cost_usd, 6),
            "latency_ms": run.latency_ms,
            "categorized_from_memory": cat_run.from_memory,
            "categorized_by_llm": cat_run.from_llm,
        },
    }


def commit_import(db: Session, batch_id: int, rows: list[CommitRow], invoice: str | None) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if not batch or batch.status != "pending":
        raise LedgerError("importação não encontrada ou já concluída")
    account = db.get(Account, batch.account_id)
    valid_cats = {c.id: c.kind for c in db.exec(select(Category))}
    existing_hashes = set(
        db.exec(
            select(Transaction.dedup_hash).where(
                Transaction.account_id == account.id, col(Transaction.dedup_hash).is_not(None)
            )
        )
    )
    created = 0
    skipped = 0
    latest: date | None = None
    groups: dict[tuple[str, int], str] = {}
    for r in rows:
        if not r.selected:
            skipped += 1
            continue
        norm = normalize_description(r.description)
        h = dedup_hash(r.date, r.amount_cents, norm, account.id)
        if h in existing_hashes and not r.force:
            skipped += 1
            continue
        category_id = (
            r.category_id if r.category_id in valid_cats and r.type != "transfer" else None
        )
        inv = None
        if account.type == "credit_card":
            # Invoices list installments with the ORIGINAL purchase date, so the statement's
            # own invoice month wins over the date-based rule when we know it.
            inv = invoice or invoice_month(r.date, account.closing_day or 1)
        group_id = None
        if r.installment_total:
            key = (norm, r.installment_total)
            group_id = groups.setdefault(key, f"import-{batch.id}-{uuid.uuid4().hex[:12]}")
        db.add(
            Transaction(
                date=r.date,
                description=r.description.strip(),
                description_normalized=norm,
                amount_cents=r.amount_cents,
                type=r.type,
                category_id=category_id,
                account_id=account.id,
                invoice_month=inv,
                installment_group_id=group_id,
                installment_number=r.installment_number,
                installment_total=r.installment_total,
                origin="import",
                import_batch_id=batch.id,
                dedup_hash=h,
            )
        )
        existing_hashes.add(h)
        # User corrections at review time teach the memory.
        if category_id is not None and r.category_id != r.suggested_category_id:
            remember_category(db, norm, category_id)
        created += 1
        latest = max(latest, r.date) if latest else r.date
    batch.imported_count = created
    batch.skipped_count = skipped
    batch.status = "committed"
    db.add(batch)
    db.commit()
    return {"batch_id": batch.id, "imported": created, "skipped": skipped,
            "latest_month": month_key(latest) if latest else None}  # fmt: skip


def undo_import(db: Session, batch_id: int) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if not batch or batch.status != "committed":
        raise LedgerError("só é possível desfazer importações concluídas")
    txs = list(db.exec(select(Transaction).where(Transaction.import_batch_id == batch_id)))
    for t in txs:
        db.delete(t)
    batch.status = "undone"
    db.add(batch)
    db.commit()
    return {"deleted": len(txs)}


def discard_preview(db: Session, batch_id: int) -> None:
    batch = db.get(ImportBatch, batch_id)
    if batch and batch.status == "pending":
        batch.status = "discarded"
        db.add(batch)
        db.commit()
