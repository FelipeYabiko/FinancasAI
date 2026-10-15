"""FinançasIA MCP server (official MCP Python SDK, stdio transport).

Exposes `query_transactions`, `get_summary` and `create_transaction`. Writing asks for
confirmation: through MCP elicitation when the client supports it, otherwise in two steps
(`create_transaction` returns a preview + action id, `confirm_action` executes it).

Run:  uv run python -m mcp_server          (uses DATABASE_URL from .env, same DB as the app)
"""

import logging

from mcp.server.mcpserver import Context, MCPServer
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import engine, init_db
from app.domain.dates import today
from app.models import PendingAction
from app.services.assistant import tools
from app.services.assistant.agent import resolve_action

log = logging.getLogger("financasia.mcp")

server = MCPServer(
    "financasia",
    title="FinançasIA",
    instructions=(
        "Ferramentas das finanças pessoais da família (valores em centavos; respostas trazem também o "
        "valor formatado em R$). Use get_summary para totais do mês e query_transactions para buscar "
        "transações. create_transaction só grava depois da confirmação do usuário."
    ),
)


def _session() -> Session:
    return Session(engine)


class Confirm(BaseModel):
    confirm: bool = Field(description="Confirmar o lançamento?")


@server.tool()
def query_transactions(
    text: str | None = None,
    category: str | None = None,
    account: str | None = None,
    type: str | None = None,
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> dict:
    """Busca transações (filtros opcionais: texto, categoria, conta, tipo income/expense/transfer,
    mês YYYY-MM, intervalo de datas YYYY-MM-DD). Devolve os itens e os totais do filtro."""
    args = {k: v for k, v in locals().items() if v is not None}
    with _session() as db:
        try:
            return tools.query_transactions(db, args)
        except tools.ToolError as exc:
            return {"error": str(exc)}


@server.tool()
def get_summary(
    month: str | None = None, category: str | None = None, account: str | None = None
) -> dict:
    """Resumo do mês (YYYY-MM; padrão: mês atual): receitas, despesas, gastos por categoria,
    orçamentos e variação vs. mês anterior. Opcionalmente filtrado por categoria ou conta."""
    args = {k: v for k, v in locals().items() if v is not None}
    with _session() as db:
        try:
            return tools.get_summary(db, args)
        except tools.ToolError as exc:
            return {"error": str(exc)}


@server.tool()
async def create_transaction(
    description: str,
    amount_cents: int,
    type: str = "expense",
    account: str | None = None,
    category: str | None = None,
    date: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Lança uma receita/despesa (amount_cents positivo; type income|expense; data YYYY-MM-DD, padrão
    hoje). Pede confirmação ao usuário antes de gravar."""
    args = {
        "description": description,
        "amount_cents": amount_cents,
        "type": type,
        "account": account,
        "category": category,
        "date": date or today().isoformat(),
    }
    with _session() as db:
        try:
            prepared = tools.prepare_write(db, "create_transaction", args)
        except tools.ToolError as exc:
            return {"status": "error", "error": str(exc)}
        action = PendingAction(
            tool=prepared.tool, arguments=prepared.arguments, summary=prepared.summary
        )
        db.add(action)
        db.commit()
        db.refresh(action)
        action_id, summary = action.id, prepared.summary

    if ctx is not None:
        try:
            answer = await ctx.elicit(f"Confirmar? {summary}", Confirm)
        except Exception as exc:  # client without elicitation support → two-step flow
            log.info("elicitation unavailable (%s); falling back to confirm_action", exc)
        else:
            confirmed = answer.action == "accept" and answer.data.confirm
            with _session() as db:
                result = resolve_action(db, action_id, confirm=confirmed)
            return {
                "status": "created" if result["status"] == "confirmed" else result["status"],
                "summary": summary,
                "result": result.get("result"),
            }
    return {
        "status": "pending_confirmation",
        "action_id": action_id,
        "summary": summary,
        "next_step": "Mostre o resumo ao usuário e, se ele concordar, chame confirm_action(action_id).",
    }


@server.tool()
def confirm_action(action_id: int, confirm: bool = True) -> dict:
    """Confirma (ou cancela, com confirm=false) um lançamento proposto por create_transaction."""
    with _session() as db:
        try:
            return resolve_action(db, action_id, confirm=confirm)
        except tools.ToolError as exc:
            return {"status": "error", "error": str(exc)}


def main() -> None:
    init_db()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
