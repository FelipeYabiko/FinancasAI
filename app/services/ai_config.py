"""Per-feature provider/model resolution: DB settings (settings screen) override `.env`."""

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


def db_recorder(db: Session):
    """Write LLMCall rows in their own session so tracing survives business rollbacks."""
    bind = db.get_bind()

    def record(call: LLMCall) -> None:
        with Session(bind) as s:
            s.add(call)
            s.commit()
            s.refresh(call)

    return record


def client_for(db: Session) -> LLMClient:
    return LLMClient(recorder=db_recorder(db))
