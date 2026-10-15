from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import current_auth
from app.api.ratelimit import ai_rate_limit
from app.db import get_session
from app.services.insights import compute_insights, narrate

router = APIRouter(prefix="/api/insights", tags=["insights"], dependencies=[Depends(current_auth)])


@router.get("")
def get_insights(db: Session = Depends(get_session)) -> dict:
    return {"items": compute_insights(db), "meta": {"llm": False}}


@router.post("/narrate", dependencies=[Depends(ai_rate_limit)])
def narrate_insights(db: Session = Depends(get_session)) -> dict:
    items, meta = narrate(db, compute_insights(db))
    return {"items": items, "meta": meta}
