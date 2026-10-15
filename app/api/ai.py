"""AI settings, connectivity test and diagnostics."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import current_auth
from app.api.ratelimit import ai_rate_limit
from app.db import get_session
from app.llm.client import LLMValidationError
from app.llm.pricing import known_models
from app.llm.prompts import DEFAULT_VERSIONS, list_versions, load_prompt
from app.llm.providers import available_providers
from app.llm.types import LLMConfigError, ProviderError
from app.schemas.api import AISettings, FeatureModel
from app.services.ai_config import FEATURES, client_for, feature_config, set_feature_config
from app.services.diagnostics import diagnostics

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(current_auth)])


@router.get("/settings")
def get_ai_settings(db: Session = Depends(get_session)) -> dict:
    return {
        "features": {
            f: dict(zip(("provider", "model"), feature_config(db, f), strict=True))
            for f in FEATURES
        },
        "providers": available_providers(),
        "models": known_models(),
        "prompt_versions": {
            f: {"default": DEFAULT_VERSIONS[f], "available": list_versions(f)} for f in FEATURES
        },
    }


@router.put("/settings")
def put_ai_settings(data: AISettings, db: Session = Depends(get_session)) -> dict:
    providers = available_providers()
    for feature in FEATURES:
        fm: FeatureModel = getattr(data, feature)
        if fm.provider not in providers:
            raise HTTPException(status_code=400, detail=f"provedor inválido: {fm.provider}")
        set_feature_config(db, feature, fm.provider, fm.model.strip())
    return get_ai_settings(db)


@router.post("/test/{feature}", dependencies=[Depends(ai_rate_limit)])
def test_feature(feature: str, db: Session = Depends(get_session)) -> dict:
    """Send a tiny ping through the configured provider/model of a feature."""
    if feature not in FEATURES:
        raise HTTPException(status_code=404, detail="feature desconhecida")
    provider, model = feature_config(db, feature)
    prompt, version = load_prompt("ping")
    try:
        result = client_for(db).call(
            feature,
            [{"role": "system", "content": prompt}, {"role": "user", "content": "ping"}],
            provider=provider,
            model=model,
            prompt_version=version,
        )
    except (LLMConfigError, ProviderError, LLMValidationError) as exc:
        return {"ok": False, "provider": provider, "model": model, "error": str(exc)}
    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "reply": result.response.text[:200],
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
    }


@router.get("/diagnostics")
def get_diagnostics(days: int = 30, db: Session = Depends(get_session)) -> dict:
    return diagnostics(db, days)
