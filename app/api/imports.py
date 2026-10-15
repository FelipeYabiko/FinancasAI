from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, col, select

from app.api.deps import current_auth
from app.api.ratelimit import ai_rate_limit
from app.db import get_session
from app.llm.types import LLMConfigError
from app.models import ImportBatch
from app.schemas.imports import CommitIn
from app.services.importer import service
from app.services.importer.pdf_text import PdfTextError

router = APIRouter(prefix="/api/import", tags=["import"], dependencies=[Depends(current_auth)])


@router.post("/preview", dependencies=[Depends(ai_rate_limit)])
async def preview(
    file: UploadFile = File(...), account_id: int = Form(...), db: Session = Depends(get_session)
) -> dict:
    data = await file.read(service.MAX_PDF_BYTES + 1)
    try:
        return service.preview_import(db, data, file.filename or "extrato.pdf", account_id)
    except PdfTextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=f"IA indisponível: {exc}") from exc
    finally:
        del data  # uploaded PDFs are never written to disk


@router.post("/{batch_id}/commit")
def commit(batch_id: int, data: CommitIn, db: Session = Depends(get_session)) -> dict:
    return service.commit_import(db, batch_id, data.rows, data.invoice_month)


@router.post("/{batch_id}/discard")
def discard(batch_id: int, db: Session = Depends(get_session)) -> dict:
    service.discard_preview(db, batch_id)
    return {"ok": True}


@router.post("/{batch_id}/undo")
def undo(batch_id: int, db: Session = Depends(get_session)) -> dict:
    return service.undo_import(db, batch_id)


@router.get("/batches")
def batches(db: Session = Depends(get_session)) -> list[dict]:
    rows = db.exec(
        select(ImportBatch)
        .where(ImportBatch.status != "discarded")
        .order_by(col(ImportBatch.id).desc())
        .limit(50)
    )
    return [b.model_dump(mode="json") for b in rows]
