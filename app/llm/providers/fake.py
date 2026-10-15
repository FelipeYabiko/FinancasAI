"""Deterministic provider for tests, local demos and CI (no network, no key)."""

import json
from collections.abc import Callable

from app.llm.providers.base import estimate_tokens
from app.llm.types import LLMResponse, Message, ToolCall

KEYWORDS = {
    "Delivery": ["ifood", "ifd*", "rappi"],
    "Transporte": ["uber", "99app", "99 tecnologia", "posto", "estac"],
    "Mercado": ["superm", "mercad", "atacadao", "hortifruti", "padaria"],
    "Assinaturas": ["netflix", "spotify", "prime", "youtube"],
    "Saúde": ["farmacia", "drogaria", "lab ", "academia"],
    "Restaurantes": ["restaurante", "cantina", "cafe"],
    "Contas e serviços": ["energia", "agua", "internet", "telefonia"],
    "Salário": ["salario"],
}


def demo_handler(messages, tools, response_schema):
    """Offline behaviour so the app and CI work without API keys: the extraction schema is
    answered by the regex baseline parser, categorization by keywords, anything else by 'pong'.
    It is NOT an LLM — evals report it as the deterministic floor."""
    import re

    from app.services.importer.baseline import parse_lines

    props = (response_schema or {}).get("properties", {})
    user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if "transactions" in props:
        m = re.search(r"Ano de referência para datas sem ano: (\d{4})", user)
        body = user.split("<<<", 1)[-1].rsplit(">>>", 1)[0]
        return {"transactions": parse_lines(body.splitlines(), int(m.group(1)) if m else None)}
    if "items" in props:
        items = []
        for line in user.split("Transações:", 1)[-1].splitlines():
            m = re.match(r"(\d+)\. \[(\w+)\] (.*)", line.strip())
            if not m:
                continue
            desc = m.group(3).lower()
            cat = "Outras receitas" if m.group(2) == "receita" else "Outros"
            for name, kws in KEYWORDS.items():
                if any(k in desc for k in kws):
                    cat = name
            items.append({"index": int(m.group(1)), "category": cat})
        return {"items": items}
    if tools:
        return _demo_agent(messages)
    return "pong"


def _demo_agent(messages):
    """Tiny rule-based stand-in for the assistant (offline demo only)."""
    import json
    import re
    from datetime import date

    last = messages[-1]
    if last["role"] == "tool":
        result = json.loads(last["content"])
        if "preview" in result:
            return f"Preparei: {result['preview']}. Confirme abaixo."
        if "expense_brl" in result:
            return (f"(modo demonstração, sem IA) Em {result.get('month', 'período')}: receitas "
                    f"{result['income_brl']}, despesas {result['expense_brl']}.")  # fmt: skip
        return "(modo demonstração) " + str(result.get("error", "ok"))
    text = last["content"].lower()
    m = re.search(
        r"gastei\s+(?:r\$\s*)?(\d+(?:[.,]\d{1,2})?)\s+(?:no|na|em|com)?\s*([\wçãéíóú ]+)", text
    )
    if m:
        from app.domain.money import parse_brl

        cents = abs(parse_brl(m.group(1).replace(".", ",")))
        acc = re.search(r"\bno\s+(\w+)\s*$", text)
        args = {"date": date.today().isoformat(), "description": m.group(2).strip().split(" ")[0].title(),
                "amount_cents": cents, "type": "expense"}  # fmt: skip
        if acc:
            args["account"] = acc.group(1)
        return {"tool_calls": [{"name": "create_transaction", "arguments": args}]}
    return {"tool_calls": [{"name": "get_summary", "arguments": {}}]}


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
            out = demo_handler(messages, tools, response_schema)
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
