"""Common provider interface + an OpenAI-compatible chat-completions implementation.

Groq, Gemini (OpenAI compatibility layer) and OpenRouter all speak the same wire format,
so they share one implementation and differ only in base URL, auth and small quirks.
"""

import json
import time
from typing import Any, Protocol

import httpx

from app.llm.types import LLMResponse, Message, ProviderError, ToolCall


class LLMProvider(Protocol):
    name: str

    def chat(
        self,
        messages: list[Message],
        model: str,
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> LLMResponse: ...


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) used for chunking and as a fallback."""
    return max(1, len(text) // 4)


class OpenAICompatibleProvider:
    name = "openai-compatible"
    base_url = ""
    supports_json_schema = True

    def __init__(self, api_key: str, http: httpx.Client | None = None):
        self.api_key = api_key
        self.http = http or httpx.Client()

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def build_payload(
        self,
        messages: list[Message],
        model: str,
        tools: list[dict] | None,
        response_schema: dict | None,
        temperature: float,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if response_schema is not None:
            if self.supports_json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "output", "schema": response_schema, "strict": False},
                }
            else:
                payload["response_format"] = {"type": "json_object"}
        return payload

    def chat(
        self,
        messages: list[Message],
        model: str,
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> LLMResponse:
        payload = self.build_payload(messages, model, tools, response_schema, temperature)
        started = time.perf_counter()
        try:
            resp = self.http.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers(),
                json=payload,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"timeout após {timeout}s", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"erro de rede: {exc}", retryable=True) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            retryable = resp.status_code == 429 or resp.status_code >= 500
            raise ProviderError(
                f"{self.name} HTTP {resp.status_code}: {resp.text[:300]}",
                status=resp.status_code,
                retryable=retryable,
            )
        return self.parse_response(resp.json(), messages, latency_ms)

    def parse_response(self, data: dict, messages: list[Message], latency_ms: int) -> LLMResponse:
        if "error" in data and not data.get("choices"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ProviderError(f"{self.name}: {msg}", retryable=True)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {"__invalid_json__": raw_args}
            tool_calls.append(
                ToolCall(
                    id=tc.get("id") or "",
                    name=fn.get("name", ""),
                    arguments=args or {},
                    raw_arguments=raw_args if isinstance(raw_args, str) else json.dumps(raw_args),
                )
            )
        usage = data.get("usage") or {}
        text = msg.get("content") or ""
        estimated = not usage
        in_tok = usage.get("prompt_tokens") or estimate_tokens(json.dumps(messages))
        out_tok = usage.get("completion_tokens") or estimate_tokens(
            text + json.dumps([t.arguments for t in tool_calls])
        )
        raw = {k: v for k, v in msg.items() if v is not None}
        raw["role"] = "assistant"
        raw.setdefault("content", text)
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            input_tokens=int(in_tok),
            output_tokens=int(out_tok),
            latency_ms=latency_ms,
            tokens_estimated=estimated,
            raw_message=raw,
            finish_reason=choice.get("finish_reason"),
        )
