"""Provider-agnostic LLM types (OpenAI chat-completions shaped messages)."""

from dataclasses import dataclass, field
from typing import Any

Message = dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    tokens_estimated: bool = False
    # The assistant message exactly as the provider returned it. Echoed back verbatim in
    # multi-turn tool loops (keeps provider-specific fields such as Gemini thought signatures).
    raw_message: Message = field(default_factory=dict)
    finish_reason: str | None = None


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        status: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after  # seconds the provider asked us to wait (429)
        # True when the provider asks for a wait far beyond a per-minute window (daily quota):
        # retrying is pointless, so the client fails fast.
        self.quota_exhausted = False


class LLMConfigError(Exception):
    """Missing API key / unknown provider: not retryable, user must fix config."""
