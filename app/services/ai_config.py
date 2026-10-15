"""Per-feature provider/model resolution: DB settings (settings screen) override `.env`."""

import threading

from sqlmodel import Session

from app.config import get_settings
from app.llm.client import LLMCall, LLMClient
from app.models import AppSetting

FEATURES = ("extraction", "categorization", "assistant", "insights")


def feature_config(db: Session, feature: str) -> tuple[str, str]:
    s = get_settings()
    provider = getattr(s, f"{feature}_provider")
    model = getattr(s, f"{feature}_model")
    p = db.get(AppSetting, f"ai.{feature}.provider")
    m = db.get(AppSetting, f"ai.{feature}.model")
    return (p.value if p else provider), (m.value if m else model)


def set_feature_config(db: Session, feature: str, provider: str, model: str) -> None:
    for key, value in ((f"ai.{feature}.provider", provider), (f"ai.{feature}.model", model)):
        row = db.get(AppSetting, key) or AppSetting(key=key, value=value)
        row.value = value
        db.add(row)
    db.commit()


# Extraction runs chunks in worker threads; SQLite connections must not be used concurrently
# (an in-memory StaticPool DB shares ONE connection), so tracing writes are serialized.
_record_lock = threading.Lock()


def db_recorder(db: Session):
    """Write LLMCall rows in their own session so tracing survives business rollbacks."""
    bind = db.get_bind()

    def record(call: LLMCall) -> None:
        with _record_lock, Session(bind, expire_on_commit=False) as s:
            s.add(call)
            s.commit()

    return record


def client_for(db: Session) -> LLMClient:
    return LLMClient(recorder=db_recorder(db))
