from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.deps import current_user
from app.api.ratelimit import ai_rate_limit
from app.db import get_session
from app.models import AssistantConversation, User
from app.services.ai_config import client_for, feature_config
from app.services.assistant.agent import resolve_action, run_agent
from app.services.assistant.tools import ToolError

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None


def _conversation(db: Session, user: User, conversation_id: int | None) -> AssistantConversation:
    if conversation_id:
        conv = db.get(AssistantConversation, conversation_id)
        if conv and conv.user_id == user.id:
            return conv
    conv = AssistantConversation(user_id=user.id, messages=[])
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/chat")
def chat(
    data: ChatIn, user: User = Depends(ai_rate_limit), db: Session = Depends(get_session)
) -> dict:
    conv = _conversation(db, user, data.conversation_id)
    provider, model = feature_config(db, "assistant")
    reply = run_agent(db, conv, data.message, client_for(db), provider, model)
    return {
        "conversation_id": conv.id,
        "reply": reply.text,
        "pending_actions": reply.pending_actions,
        "steps": [
            {
                "tool": s.tool,
                "arguments": s.arguments,
                "error": s.error,
                "pending_action_id": s.pending_action_id,
            }
            for s in reply.steps
        ],
        "hit_limit": reply.hit_limit,
        "stats": {
            "llm_calls": reply.llm_calls,
            "cost_usd": round(reply.cost_usd, 6),
            "latency_ms": reply.latency_ms,
        },
    }


@router.post("/actions/{action_id}/{decision}")
def decide(
    action_id: int,
    decision: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> dict:
    if decision not in ("confirm", "cancel"):
        raise HTTPException(status_code=404, detail="decisão inválida")
    try:
        return resolve_action(db, action_id, confirm=decision == "confirm")
    except ToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
