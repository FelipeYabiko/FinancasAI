"""End-to-end: a real MCP client talks to the server over stdio."""

import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import ElicitResult
from sqlmodel import Session, create_engine, select

from app.db import init_db
from app.domain.dates import today
from app.models import Account, Transaction
from app.schemas.api import TransactionIn
from app.services import ledger

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def db_url(tmp_path):
    url = f"sqlite:///{tmp_path / 'mcp.db'}"
    eng = create_engine(url)
    init_db(eng)
    with Session(eng) as db:
        acc = Account(name="Conta Corrente", type="checking")
        db.add(acc)
        db.commit()
        ledger.create_transaction(
            db,
            TransactionIn(
                date=today(),
                description="Mercado",
                amount_cents=12345,
                type="expense",
                account_id=acc.id,
            ),
        )
    return url


def _run(db_url, scenario, elicitation=None):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server"],
        cwd=str(ROOT),
        env={**os.environ, "DATABASE_URL": db_url},
    )

    async def main():
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, elicitation_callback=elicitation) as session,
        ):
            await session.initialize()
            return await scenario(session)

    return anyio.run(main)


def _payload(result):
    if getattr(result, "structured_content", None):
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


def test_mcp_answers_how_much_spent_this_month(db_url):
    async def scenario(session):
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert {"query_transactions", "get_summary", "create_transaction"} <= names
        return _payload(await session.call_tool("get_summary", {}))

    summary = _run(db_url, scenario)
    assert summary["expense_cents"] == 12345
    assert summary["expense_brl"] == "R$ 123,45"


def test_mcp_create_transaction_with_elicitation(db_url):
    async def accept(context, params):
        assert "R$ 10,00" in params.message
        return ElicitResult(action="accept", content={"confirm": True})

    async def scenario(session):
        return _payload(
            await session.call_tool(
                "create_transaction",
                {"description": "Padaria", "amount_cents": 1000, "account": "conta"},
            )
        )

    res = _run(db_url, scenario, elicitation=accept)
    assert res["status"] == "created"
    eng = create_engine(db_url)
    with Session(eng) as db:
        assert (
            db.exec(select(Transaction).where(Transaction.description == "Padaria")).first().origin
            == "assistant"
        )


def test_mcp_create_transaction_declined_and_two_step(db_url):
    async def decline(context, params):
        return ElicitResult(action="decline")

    async def scenario(session):
        return _payload(
            await session.call_tool("create_transaction", {"description": "X", "amount_cents": 500})
        )

    assert _run(db_url, scenario, elicitation=decline)["status"] == "cancelled"

    async def two_step(session):  # client without elicitation support
        first = _payload(
            await session.call_tool("create_transaction", {"description": "Y", "amount_cents": 700})
        )
        assert first["status"] == "pending_confirmation"
        return _payload(
            await session.call_tool("confirm_action", {"action_id": first["action_id"]})
        )

    assert _run(db_url, two_step)["status"] == "confirmed"
    with Session(create_engine(db_url)) as db:
        descs = {t.description for t in db.exec(select(Transaction))}
    assert "Y" in descs and "X" not in descs
