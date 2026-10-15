"""Application settings, read from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_env: str = "development"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'financasia.db'}"
    secret_key: str = "change-me-in-production"
    session_max_age_days: int = 30
    cookie_secure: bool = False
    timezone: str = "America/Sao_Paulo"

    # Provider API keys (backend only, never sent to the browser)
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    # Provider + model per feature. Model names live ONLY here / in the DB settings.
    extraction_provider: str = "groq"
    extraction_model: str = "openai/gpt-oss-20b"
    categorization_provider: str = "groq"
    categorization_model: str = "openai/gpt-oss-20b"
    assistant_provider: str = "groq"
    assistant_model: str = "openai/gpt-oss-120b"
    insights_provider: str = "groq"
    insights_model: str = "openai/gpt-oss-20b"

    # LLM client behaviour
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_log_payloads: bool = False
    extraction_chunk_tokens: int = 1500

    # Rate limit for AI endpoints (requests per minute per user)
    ai_rate_limit_per_minute: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
