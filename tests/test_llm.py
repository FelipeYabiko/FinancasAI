import json

import httpx
import pytest
from pydantic import BaseModel
from sqlmodel import select

from app.config import Settings
from app.llm.client import LLMClient, LLMValidationError, extract_json
from app.llm.pricing import estimate_cost_usd
from app.llm.prompts import list_versions, load_prompt
from app.llm.providers import clear_provider_overrides, register_provider
from app.llm.providers.fake import FakeProvider
from app.llm.providers.groq import GroqProvider
from app.llm.providers.openrouter import OpenRouterProvider
from app.llm.types import LLMConfigError, LLMResponse, ProviderError
from app.models import LLMCall


class Out(BaseModel):
    answer: int


@pytest.fixture(autouse=True)
def _clean():
    yield
    clear_provider_overrides()


def make_client(records, **settings):
    return LLMClient(recorder=records.append, settings=Settings(**settings), sleep=lambda _: None)


def call(client, provider="fake", model="fake", **kw):
    return client.call(
        "extraction",
        [{"role": "user", "content": "x"}],
        provider=provider,
        model=model,
        prompt_version="extraction.v1",
        **kw,
    )


def test_retry_on_rate_limit_then_success():
    fake = FakeProvider(script=[ProviderError("429", 429, True), ProviderError("503", 503, True), "ok"])
    register_provider("fake", fake)
    records = []
    res = call(make_client(records))
    assert res.response.text == "ok"
    assert len(fake.calls) == 3
    assert records[-1].status == "ok"
    assert records[-1].attempts == 3


def test_non_retryable_error_is_recorded():
    register_provider("fake", FakeProvider(script=[ProviderError("400 bad", 400, False)]))
    records = []
    with pytest.raises(ProviderError):
        call(make_client(records))
    assert records[0].status == "error"
    assert "400" in records[0].error_message


def test_retries_exhausted():
    register_provider("fake", FakeProvider(script=[ProviderError("429", 429, True)] * 5))
    records = []
    with pytest.raises(ProviderError):
        call(make_client(records, llm_max_retries=2))
    assert records[0].attempts == 3


def test_validation_corrective_retry():
    fake = FakeProvider(script=['{"answer": "not a number"}', '```json\n{"answer": 42}\n```'])
    register_provider("fake", fake)
    records = []
    res = call(make_client(records), response_model=Out)
    assert res.parsed == Out(answer=42)
    assert res.validation_retries == 1
    assert [r.status for r in records] == ["validation_error", "ok"]
    # the second request contains the validation error fed back to the model
    second = fake.calls[1]["messages"]
    assert "validação" in second[-1]["content"]
    assert "answer" in second[-1]["content"]


def test_validation_fails_twice():
    register_provider("fake", FakeProvider(script=["nope", "still nope"]))
    records = []
    with pytest.raises(LLMValidationError):
        call(make_client(records), response_model=Out)
    assert [r.status for r in records] == ["validation_error", "validation_error"]


def test_payloads_not_logged_by_default():
    register_provider("fake", FakeProvider(script=["ok", "ok"]))
    records = []
    call(make_client(records))
    assert records[0].request_payload is None
    assert records[0].response_payload is None
    call(make_client(records, llm_log_payloads=True))
    assert "x" in records[1].request_payload


def test_missing_key_is_config_error():
    records = []
    with pytest.raises(LLMConfigError):
        call(make_client(records), provider="groq", model="openai/gpt-oss-20b")
    assert records[0].status == "error"


def test_cost_estimate():
    assert estimate_cost_usd("groq", "openai/gpt-oss-20b", 1_000_000, 1_000_000) == pytest.approx(0.375)
    assert estimate_cost_usd("groq", "unknown-model", 1000, 1000) == 0.0


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('Claro! {"a": [1]} pronto') == '{"a": [1]}'


def test_prompts_versioned():
    text, version = load_prompt("ping")
    assert version == "ping.v1"
    assert "pong" in text
    assert "v1" in list_versions("ping")


# ---------- wire format of the OpenAI-compatible providers ----------
def _transport(status, body, seen):
    def handler(request: httpx.Request):
        seen.append(json.loads(request.content))
        seen.append(dict(request.headers))
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def test_openai_compatible_parse_tool_calls_and_usage():
    seen = []
    body = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "c1", "type": "function",
                         "function": {"name": "get_summary", "arguments": '{"month": "2026-10"}'}}
                    ],  # fmt: skip
                    "extra_content": {"google": {"thought_signature": "sig"}},
                },
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }
    p = OpenRouterProvider("k", http=httpx.Client(transport=_transport(200, body, seen)))
    r = p.chat([{"role": "user", "content": "oi"}], "m", tools=[{"type": "function"}])
    assert r.tool_calls[0].name == "get_summary"
    assert r.tool_calls[0].arguments == {"month": "2026-10"}
    assert (r.input_tokens, r.output_tokens) == (120, 30)
    assert r.raw_message["extra_content"]["google"]["thought_signature"] == "sig"
    assert seen[0]["tool_choice"] == "auto"
    assert seen[1]["authorization"] == "Bearer k"


def test_groq_uses_json_object_and_429_is_retryable():
    seen = []
    p = GroqProvider("k", http=httpx.Client(transport=_transport(429, {"error": "slow"}, seen)))
    with pytest.raises(ProviderError) as exc:
        p.chat([{"role": "user", "content": "x"}], "m", response_schema={"type": "object"})
    assert exc.value.retryable
    assert seen[0]["response_format"] == {"type": "json_object"}


def test_missing_usage_is_estimated():
    body = {"choices": [{"message": {"role": "assistant", "content": "olá mundo"}}]}
    p = GroqProvider("k", http=httpx.Client(transport=_transport(200, body, [])))
    r = p.chat([{"role": "user", "content": "x" * 400}], "m")
    assert r.tokens_estimated
    assert r.input_tokens > 50


# ---------- API: test call shows up in LLMCall + diagnostics ----------
def test_ai_test_endpoint_records_llmcall(client, db):
    register_provider(
        "fake", FakeProvider(script=[LLMResponse(text="pong", input_tokens=12, output_tokens=2, latency_ms=150)])
    )
    client.put(
        "/api/ai/settings",
        json={f: {"provider": "fake", "model": "fake"} for f in ("extraction", "categorization", "assistant", "insights")},
    )
    r = client.post("/api/ai/test/extraction").json()
    assert r["ok"] and r["reply"] == "pong"
    rows = db.exec(select(LLMCall)).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.feature, row.prompt_version, row.input_tokens, row.output_tokens, row.latency_ms) == (
        "extraction", "ping.v1", 12, 2, 150,
    )  # fmt: skip
    d = client.get("/api/ai/diagnostics").json()
    assert d["total_calls"] == 1
    assert d["p95_ms"] == 150
    assert d["by_feature"][0]["feature"] == "extraction"


def test_ai_test_without_key_reports_error(client, db):
    r = client.post("/api/ai/test/assistant").json()
    assert r["ok"] is False
    assert "chave" in r["error"]
    d = client.get("/api/ai/diagnostics").json()
    assert d["error_rate"] == 100.0
    assert d["recent_failures"][0]["feature"] == "assistant"


def test_ai_rate_limit(client, monkeypatch):
    from app.api import ratelimit
    from app.config import get_settings

    ratelimit.reset_rate_limits()
    monkeypatch.setattr(get_settings(), "ai_rate_limit_per_minute", 2)
    codes = [client.post("/api/ai/test/assistant").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    ratelimit.reset_rate_limits()
