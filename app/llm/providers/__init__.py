"""Provider registry."""

from app.config import get_settings
from app.llm.providers.base import LLMProvider
from app.llm.providers.fake import FakeProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.groq import GroqProvider
from app.llm.providers.openrouter import OpenRouterProvider
from app.llm.types import LLMConfigError

PROVIDERS = {"groq": GroqProvider, "gemini": GeminiProvider, "openrouter": OpenRouterProvider}
_overrides: dict[str, LLMProvider] = {}


def register_provider(name: str, provider: LLMProvider) -> None:
    """Inject a provider instance (tests, evals with a fake provider)."""
    _overrides[name] = provider


def clear_provider_overrides() -> None:
    _overrides.clear()


def api_key_for(name: str) -> str:
    s = get_settings()
    return {
        "groq": s.groq_api_key,
        "gemini": s.gemini_api_key,
        "openrouter": s.openrouter_api_key,
    }.get(name, "")


def available_providers() -> dict[str, bool]:
    """Provider -> whether it is usable (key configured)."""
    out = {name: bool(api_key_for(name)) for name in PROVIDERS}
    if get_settings().app_env != "production" or "fake" in _overrides:
        out["fake"] = True
    return out


def get_provider(name: str) -> LLMProvider:
    if name in _overrides:
        return _overrides[name]
    if name == "fake":
        return FakeProvider()
    cls = PROVIDERS.get(name)
    if not cls:
        raise LLMConfigError(f"provedor desconhecido: {name}")
    key = api_key_for(name)
    if not key:
        raise LLMConfigError(f"chave de API do provedor '{name}' não configurada no .env")
    return cls(key)
