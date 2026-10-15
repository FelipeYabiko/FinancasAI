"""Central LLM client: timeout, retries with exponential backoff, schema validation with
one corrective retry, and tracing of every call into `LLMCall`."""

import contextlib
import json
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.llm.pricing import estimate_cost_usd
from app.llm.providers import get_provider
from app.llm.types import LLMConfigError, LLMResponse, Message, ProviderError
from app.models import LLMCall

Recorder = Callable[[LLMCall], None]
MAX_RETRY_AFTER_SECONDS = 60.0


class LLMValidationError(Exception):
    def __init__(self, message: str, raw_text: str):
        super().__init__(message)
        self.raw_text = raw_text


@dataclass
class LLMResult:
    response: LLMResponse
    parsed: BaseModel | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    validation_retries: int = 0
    records: list[LLMCall] = field(default_factory=list)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> str:
    """Strip markdown fences / chatter around a JSON document."""
    s = _FENCE_RE.sub("", text.strip()).strip()
    if s and s[0] in "{[":
        return s
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    if not starts:
        return s
    start = min(starts)
    end = max(s.rfind("}"), s.rfind("]"))
    return s[start : end + 1] if end > start else s


class LLMClient:
    def __init__(
        self,
        recorder: Recorder | None = None,
        settings: Settings | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.recorder = recorder
        self.settings = settings or get_settings()
        self.sleep = sleep

    # ---- tracing ----
    def _record(self, result: LLMResult | None, **fields) -> LLMCall:
        call = LLMCall(**fields)
        if self.recorder:
            with contextlib.suppress(Exception):  # tracing must never break the feature
                self.recorder(call)
        if result is not None:
            result.records.append(call)
        return call

    def _payload(self, value) -> str | None:
        if not self.settings.llm_log_payloads:
            return None
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)[:200_000]

    # ---- transport with retry ----
    def _chat_with_retry(self, provider, model, messages, tools, schema, temperature):
        attempts = 0
        max_retries = self.settings.llm_max_retries
        while True:
            attempts += 1
            try:
                resp = provider.chat(
                    messages,
                    model,
                    tools=tools,
                    response_schema=schema,
                    temperature=temperature,
                    timeout=self.settings.llm_timeout_seconds,
                )
                return resp, attempts
            except ProviderError as exc:
                # Rate limits get a larger budget: waiting is cheap, failing a whole import isn't.
                budget = max_retries + (3 if exc.status == 429 else 0)
                if not exc.retryable or attempts > budget:
                    exc.attempts = attempts
                    raise
                delay = min(2 ** (attempts - 1), 20)
                if exc.retry_after is not None:
                    # Honor the provider's own wait time (Groq: "try again in 5.9s").
                    delay = max(delay, min(exc.retry_after, MAX_RETRY_AFTER_SECONDS))
                self.sleep(delay + random.uniform(0, 0.5))

    # ---- public API ----
    def call(
        self,
        feature: str,
        messages: list[Message],
        *,
        provider: str,
        model: str,
        prompt_version: str,
        tools: list[dict] | None = None,
        response_model: type[BaseModel] | None = None,
        temperature: float = 0.0,
    ) -> LLMResult:
        base = {
            "feature": feature,
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
        }
        try:
            prov = get_provider(provider)
        except LLMConfigError as exc:
            self._record(None, **base, status="error", error_message=str(exc))
            raise

        schema = response_model.model_json_schema() if response_model else None
        result = LLMResult(response=LLMResponse(text=""))
        convo = list(messages)
        for validation_round in range(2):
            try:
                resp, attempts = self._chat_with_retry(
                    prov, model, convo, tools, schema, temperature
                )
            except ProviderError as exc:
                self._record(
                    result,
                    **base,
                    status="error",
                    attempts=getattr(exc, "attempts", 1),
                    error_message=str(exc)[:1000],
                    request_payload=self._payload(convo),
                )
                raise
            cost = estimate_cost_usd(provider, model, resp.input_tokens, resp.output_tokens)
            result.response = resp
            result.calls += 1
            result.cost_usd += cost
            result.latency_ms += resp.latency_ms
            result.input_tokens += resp.input_tokens
            result.output_tokens += resp.output_tokens
            common = {
                **base,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "cost_usd": cost,
                "latency_ms": resp.latency_ms,
                "attempts": attempts,
                "request_payload": self._payload(convo),
                "response_payload": self._payload(resp.raw_message),
            }
            if response_model is None or resp.tool_calls:
                self._record(result, **common, status="ok")
                return result
            try:
                result.parsed = response_model.model_validate_json(extract_json(resp.text))
                self._record(result, **common, status="ok")
                return result
            except ValidationError as exc:
                err = _short_validation_error(exc)
                self._record(result, **common, status="validation_error", error_message=err)
                if validation_round == 1:
                    raise LLMValidationError(err, resp.text) from exc
                result.validation_retries += 1
                # One corrective retry: give the model its own output and the error.
                convo = [
                    *convo,
                    {"role": "assistant", "content": resp.text or ""},
                    {
                        "role": "user",
                        "content": (
                            "Sua resposta não passou na validação do schema JSON:\n"
                            f"{err}\n"
                            "Responda novamente APENAS com o JSON corrigido, sem texto extra."
                        ),
                    },
                ]
        raise AssertionError("unreachable")  # pragma: no cover


def _short_validation_error(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors()[:8]:
        loc = ".".join(str(x) for x in e["loc"]) or "(raiz)"
        parts.append(f"{loc}: {e['msg']}")
    return "; ".join(parts)[:1000]
