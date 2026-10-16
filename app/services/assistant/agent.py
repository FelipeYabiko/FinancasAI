"""Assistant agent loop: compact context + tools on demand + confirmation for writes."""

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from app.domain.dates import month_key, today
from app.domain.money import format_brl
from app.llm.client import LLMClient
from app.llm.prompts import load_prompt
from app.llm.types import LLMConfigError, ProviderError
from app.models import Account, AssistantConversation, Category, Goal, PendingAction
from app.services.assistant.tools import (
    READ_TOOLS,
    TOOL_SPECS,
    WRITE_TOOLS,
    ToolError,
    execute_write,
    prepare_write,
    run_read_tool,
)
from app.services.dashboard import budgets_for_month
from app.services.ledger import account_balances

MAX_ITERATIONS = 6
WEEKDAYS = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]
LIMIT_MESSAGE = (
    "Não consegui concluir esse pedido em poucas etapas. Pode reformular de forma mais "
    "específica (por exemplo, dizendo o mês, a conta ou a categoria)?"
)
PENDING_TTL = timedelta(minutes=30)


@dataclass
class AgentStep:
    tool: str
    arguments: dict
    result: dict
    pending_action_id: int | None = None
    error: bool = False


@dataclass
class AgentReply:
    text: str
    conversation_id: int | None
    pending_actions: list[dict] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    iterations: int = 0
    llm_calls: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    hit_limit: bool = False
    error: str | None = None  # provider failure that ended the turn (not shown to the user)
    provider_failure: bool = False  # rate limit / outage: says nothing about the model
    quota_exhausted: bool = False


def build_context(db: Session, on: date | None = None) -> str:
    """Compact snapshot sent every turn. No transactions: those come via tools."""
    on = on or today()
    month = month_key(on)
    balances = account_balances(db, until=on)
    accounts = list(db.exec(select(Account).where(Account.archived == False)))  # noqa: E712
    cats = list(db.exec(select(Category)))
    goals = list(db.exec(select(Goal)))
    lines = [
        f"Hoje: {on.isoformat()} ({WEEKDAYS[on.weekday()]}). Mês atual: {month}.",
        "Contas (id · nome · tipo · saldo):",
    ]
    for a in accounts:
        extra = (
            f" · fecha dia {a.closing_day}, vence dia {a.due_day}"
            if a.type == "credit_card"
            else ""
        )
        lines.append(f"- {a.id} · {a.name} · {a.type} · {format_brl(balances.get(a.id, 0))}{extra}")
    lines.append(
        "Categorias de despesa: "
        + ", ".join(f"{c.name} ({c.id})" for c in cats if c.kind == "expense")
    )
    lines.append(
        "Categorias de receita: "
        + ", ".join(f"{c.name} ({c.id})" for c in cats if c.kind == "income")
    )
    budgets = budgets_for_month(db, month)
    if budgets:
        names = {c.id: c.name for c in cats}
        lines.append(
            "Orçamentos do mês: "
            + "; ".join(
                f"{names.get(b['category_id'])} {format_brl(b['spent_cents'])} de {format_brl(b['limit_cents'])}"
                for b in budgets
            )
        )
    if goals:
        lines.append(
            "Metas: "
            + "; ".join(
                f"{g.name} ({g.id}) {format_brl(g.current_cents)} de {format_brl(g.target_cents)}"
                for g in goals
            )
        )
    return "\n".join(lines)


def _tool_message(call_id: str, name: str, payload: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "name": name,
        "content": json.dumps(payload, ensure_ascii=False, default=str),
    }


def run_agent(
    db: Session,
    conversation: AssistantConversation,
    user_message: str,
    client: LLMClient,
    provider: str,
    model: str,
    *,
    prompt_version: str | None = None,
    on: date | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> AgentReply:
    system, version = load_prompt(
        "assistant", prompt_version.split(".")[-1] if prompt_version else None
    )
    system = f"{system}\n\n## Contexto atual\n{build_context(db, on)}"
    history: list[dict] = list(conversation.messages or [])
    history.append({"role": "user", "content": user_message.strip()[:4000]})
    reply = AgentReply(text="", conversation_id=conversation.id)

    for _ in range(max_iterations):
        reply.iterations += 1
        try:
            res = client.call(
                "assistant",
                [{"role": "system", "content": system}, *history],
                provider=provider,
                model=model,
                prompt_version=version,
                tools=TOOL_SPECS,
                temperature=0.1,
            )
        except (ProviderError, LLMConfigError) as exc:
            reply.error = str(exc)[:500]
            # rate limit / outage; a 400 can be our own request's fault and stays a failure
            reply.provider_failure = isinstance(exc, ProviderError) and exc.retryable
            reply.quota_exhausted = getattr(exc, "quota_exhausted", False)
            reply.text = f"Não consegui falar com o modelo de IA agora ({exc.__class__.__name__}). Tente de novo em instantes."
            break
        reply.llm_calls += res.calls
        reply.cost_usd += res.cost_usd
        reply.latency_ms += res.latency_ms
        resp = res.response
        history.append(resp.raw_message or {"role": "assistant", "content": resp.text})
        if not resp.tool_calls:
            reply.text = (resp.text or "").strip()
            break
        for call in resp.tool_calls:
            args = call.arguments if isinstance(call.arguments, dict) else {}
            step = AgentStep(tool=call.name, arguments=args, result={})
            try:
                if "__invalid_json__" in args:
                    raise ToolError("argumentos não são JSON válido")
                if call.name in READ_TOOLS:
                    step.result = run_read_tool(db, call.name, args)
                elif call.name in WRITE_TOOLS:
                    prepared = prepare_write(db, call.name, args)
                    action = PendingAction(
                        conversation_id=conversation.id,
                        tool=prepared.tool,
                        arguments=prepared.arguments,
                        summary=prepared.summary,
                    )
                    db.add(action)
                    db.commit()
                    db.refresh(action)
                    step.pending_action_id = action.id
                    step.result = {
                        "status": "aguardando_confirmacao",
                        "action_id": action.id,
                        "preview": prepared.summary,
                        "note": "NÃO executado ainda. O usuário precisa confirmar na interface.",
                    }
                    reply.pending_actions.append(_action_dict(action))
                else:
                    raise ToolError(f"ferramenta desconhecida: {call.name}")
            except ToolError as exc:
                step.error = True
                step.result = {"error": str(exc)}
            reply.steps.append(step)
            history.append(_tool_message(call.id, call.name, step.result))
    else:
        reply.hit_limit = True
        reply.text = LIMIT_MESSAGE
    if not reply.text and reply.pending_actions:
        reply.text = "Confira a prévia abaixo e confirme para eu executar."

    conversation.messages = history[-60:]  # bounded memory
    conversation.updated_at = datetime.now(UTC)
    db.add(conversation)
    db.commit()
    return reply


def _action_dict(a: PendingAction) -> dict:
    return {
        "id": a.id,
        "tool": a.tool,
        "summary": a.summary,
        "status": a.status,
        "arguments": a.arguments,
    }


def resolve_action(db: Session, action_id: int, confirm: bool) -> dict:
    """Confirm (execute) or cancel a pending action, and tell the conversation."""
    action = db.get(PendingAction, action_id)
    if not action:
        raise ToolError("ação não encontrada")
    if action.status != "pending":
        raise ToolError(f"ação já está '{action.status}'")
    created = (
        action.created_at if action.created_at.tzinfo else action.created_at.replace(tzinfo=UTC)
    )
    if datetime.now(UTC) - created > PENDING_TTL:
        action.status = "expired"
        db.add(action)
        db.commit()
        raise ToolError("a prévia expirou; peça novamente ao assistente")
    if confirm:
        try:
            # Re-validate against the current state before executing.
            prepared = prepare_write(db, action.tool, _reprepare_args(action))
            action.result = execute_write(db, action.tool, prepared.arguments)
            action.status = "confirmed"
            note = f"[sistema] O usuário CONFIRMOU a ação {action.id} ({action.summary}). Executada com sucesso."
        except ToolError as exc:
            action.status = "failed"
            action.result = {"error": str(exc)}
            note = f"[sistema] A ação {action.id} falhou ao executar: {exc}"
    else:
        action.status = "cancelled"
        note = f"[sistema] O usuário CANCELOU a ação {action.id} ({action.summary}). Nada foi alterado."
    db.add(action)
    if action.conversation_id:
        conv = db.get(AssistantConversation, action.conversation_id)
        if conv:
            conv.messages = [*conv.messages, {"role": "user", "content": note}]
            db.add(conv)
    db.commit()
    return _action_dict(action) | {"result": action.result}


def _reprepare_args(action: PendingAction) -> dict:
    """Map normalized (id-based) arguments back to the tool's input shape."""
    a = dict(action.arguments)
    t = action.tool
    if t == "create_transaction":
        return {**a, "account": a["account_id"], "category": a.get("category_id")}
    if t == "create_installment_purchase":
        return {**a, "account": a["account_id"], "category": a.get("category_id")}
    if t == "create_transfer":
        return {**a, "from_account": a["from_account_id"], "to_account": a["to_account_id"]}
    if t == "set_budget":
        return {**a, "category": a["category_id"]}
    if t == "update_goal":
        return {"goal": a["goal_id"], "current_cents": a["current_cents"]}
    return a
