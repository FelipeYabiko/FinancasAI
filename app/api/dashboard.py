import json
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from app.api.deps import current_auth
from app.db import get_session
from app.services import backup
from app.services.dashboard import dashboard
from app.services.recurring import run_recurring

router = APIRouter(prefix="/api", tags=["dashboard"], dependencies=[Depends(current_auth)])


@router.get("/dashboard")
def get_dashboard(month: str | None = None, db: Session = Depends(get_session)) -> dict:
    run_recurring(db)  # cheap + idempotent: recurring rules launch when the month arrives
    return dashboard(db, month)


@router.get("/backup/json")
def export_json(db: Session = Depends(get_session)) -> Response:
    body = json.dumps(backup.export_json(db), ensure_ascii=False, indent=2)
    name = f"financasia-backup-{date.today().isoformat()}.json"
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/backup/json")
async def import_json(file: UploadFile = File(...), db: Session = Depends(get_session)) -> dict:
    try:
        data = json.loads(await file.read())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="arquivo não é um JSON válido") from exc
    return {"restored": backup.import_json(db, data)}


@router.get("/backup/csv")
def export_csv(db: Session = Depends(get_session)) -> Response:
    name = f"financasia-transacoes-{date.today().isoformat()}.csv"
    return Response(
        "﻿" + backup.export_csv(db),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
