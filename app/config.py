"""Application settings, read from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # env_ignore_empty: `cp .env.example .env` (all values blank) must fall back to the defaults
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    # Core
    app_env: str = "development"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'financasia.db'}"
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
    # reasoning_effort for reasoning models that accept it (Groq gpt-oss): low | medium | high | ""
    llm_reasoning_effort: str = "low"
    extraction_chunk_tokens: int = 1500
    # Chunks extracted in parallel. Lower it on low rate-limit tiers (e.g. Groq free: 8k tokens/min).
    extraction_concurrency: int = 4

    # Event-driven integration with the Java alerts-service (both optional)
    rabbitmq_url: str = (
        ""  # e.g. amqp://guest:guest@localhost:5672/  (empty = events stay in the outbox)
    )
    events_exchange: str = "financasia.events"
    alerts_service_url: str = ""  # e.g. http://localhost:8081
    alerts_internal_token: str = ""

    # Rate limit for AI endpoints (requests per minute per user)
    ai_rate_limit_per_minute: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
