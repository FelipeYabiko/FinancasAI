"""Deterministic provider for tests, local demos and CI (no network, no key)."""

import json
from collections.abc import Callable

from app.llm.providers.base import estimate_tokens
from app.llm.types import LLMResponse, Message, ToolCall

Handler = Callable[[list[Message], list[dict] | None, dict | None], LLMResponse | str | dict]


class FakeProvider:
    name = "fake"

    def __init__(self, handler: Handler | None = None, script: list | None = None):
        self.handler = handler
        self.script = list(script or [])
        self.calls: list[dict] = []

    def chat(
        self, messages, model, tools=None, response_schema=None, temperature=0.0, timeout=60.0
    ):
        self.calls.append({"messages": messages, "model": model, "tools": tools})
        if self.script:
            out = self.script.pop(0)
        elif self.handler:
            out = self.handler(messages, tools, response_schema)
        else:
            out = "ok"
        if isinstance(out, Exception):
            raise out
        if isinstance(out, LLMResponse):
            resp = out
        elif isinstance(out, dict) and "tool_calls" in out:
            resp = LLMResponse(
                text=out.get("text", ""),
                tool_calls=[
                    ToolCall(id=f"call_{i}", name=tc["name"], arguments=tc["arguments"])
                    for i, tc in enumerate(out["tool_calls"])
                ],
            )
        else:
            resp = LLMResponse(text=out if isinstance(out, str) else json.dumps(out))
        if not resp.raw_message:
            resp.raw_message = {"role": "assistant", "content": resp.text}
            if resp.tool_calls:
                resp.raw_message["tool_calls"] = [
                    {"id": t.id, "type": "function",
                     "function": {"name": t.name, "arguments": json.dumps(t.arguments)}}
                    for t in resp.tool_calls
                ]  # fmt: skip
        resp.input_tokens = resp.input_tokens or estimate_tokens(json.dumps(messages))
        resp.output_tokens = resp.output_tokens or estimate_tokens(resp.text or "x")
        resp.latency_ms = resp.latency_ms or 1
        return resp
