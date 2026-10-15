from datetime import timedelta

import pytest

from app.domain.dates import month_key, today
from app.llm.providers import register_provider
from app.llm.providers.fake import FakeProvider

FEATURES = ("extraction", "categorization", "assistant", "insights")


def call(tool, **arguments):
    return {"tool_calls": [{"name": tool, "arguments": arguments}]}


@pytest.fixture
def setup(client, accounts, categories):
    client.put(
        "/api/ai/settings", json={f: {"provider": "fake", "model": "fake"} for f in FEATURES}
    )
    nubank = client.post(
        "/api/accounts",
        json={"name": "Nubank", "type": "credit_card", "closing_day": 3, "due_day": 10},
    ).json()
    return {**accounts, "nubank": nubank, "cats": categories}


def chat(client, message, conversation_id=None):
    r = client.post(
        "/api/assistant/chat", json={"message": message, "conversation_id": conversation_id}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_create_expense_requires_confirmation(client, setup):
    yesterday = (today() - timedelta(days=1)).isoformat()
    fake = FakeProvider(script=[
        call("create_transaction", date=yesterday, description="Mercado", amount_cents=4500,
             type="expense", account="nubank", category="mercado"),
        "Vou lançar R$ 45,00 no Nubank. Confirma?",
    ])  # fmt: skip
    register_provider("fake", fake)
    res = chat(client, "gastei 45 no mercado ontem no Nubank")
    assert len(res["pending_actions"]) == 1
    action = res["pending_actions"][0]
    assert "R$ 45,00" in action["summary"]
    assert "Nubank" in action["summary"]
    # nothing written before confirmation
    assert client.get("/api/transactions", params={"q": "Mercado"}).json()["total"] == 0
    # the model was told the action is pending, not done
    tool_msg = fake.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "aguardando_confirmacao" in tool_msg["content"]

    done = client.post(f"/api/assistant/actions/{action['id']}/confirm").json()
    assert done["status"] == "confirmed"
    txs = client.get("/api/transactions", params={"q": "Mercado"}).json()["items"]
    assert len(txs) == 1
    tx = txs[0]
    assert (tx["date"], tx["amount_cents"], tx["origin"]) == (yesterday, -4500, "assistant")
    assert tx["account_id"] == setup["nubank"]["id"]
    assert tx["category_id"] == setup["cats"]["Mercado"]
    # can't confirm twice
    assert client.post(f"/api/assistant/actions/{action['id']}/confirm").status_code == 400


def test_question_answered_from_tools(client, setup):
    acc = setup["checking"]["id"]
    for amt in (4590, 3210):
        client.post("/api/transactions", json={
            "date": today().isoformat(), "description": "iFood", "amount_cents": amt, "type": "expense",
            "account_id": acc, "category_id": setup["cats"]["Delivery"]})  # fmt: skip
    fake = FakeProvider(script=[call("get_summary", month=month_key(today()), category="Delivery"),
                                "Você gastou R$ 78,00 com delivery este mês."])  # fmt: skip
    register_provider("fake", fake)
    res = chat(client, "quanto gastei com delivery esse mês?")
    assert res["steps"][0]["tool"] == "get_summary"
    assert res["pending_actions"] == []
    tool_result = fake.calls[1]["messages"][-1]["content"]
    assert '"expense_cents": 7800' in tool_result
    assert "R$ 78,00" in res["reply"]
    # the context sent to the model never dumps transactions
    system = fake.calls[0]["messages"][0]["content"]
    assert "iFood" not in system


def test_installment_purchase_on_card(client, setup):
    fake = FakeProvider(script=[
        call("create_installment_purchase", date=today().isoformat(), description="TV",
             total_cents=300000, installments=10, account="Nubank", category="Compras"),
        "Confirma a compra da TV em 10x?",
    ])  # fmt: skip
    register_provider("fake", fake)
    res = chat(client, "comprei uma TV de 3 mil em 10x no cartão")
    action = res["pending_actions"][0]
    assert "10x de R$ 300,00" in action["summary"]
    client.post(f"/api/assistant/actions/{action['id']}/confirm")
    txs = client.get("/api/transactions", params={"q": "TV"}).json()["items"]
    assert len(txs) == 10
    assert sum(t["amount_cents"] for t in txs) == -300000
    assert len({t["invoice_month"] for t in txs}) == 10


def test_card_inferred_when_only_one_card(client, accounts, categories):
    client.put(
        "/api/ai/settings", json={f: {"provider": "fake", "model": "fake"} for f in FEATURES}
    )
    register_provider("fake", FakeProvider(script=[
        call("create_installment_purchase", date=today().isoformat(), description="TV",
             total_cents=300000, installments=10), "ok"]))  # fmt: skip
    res = chat(client, "comprei uma TV de 3 mil em 10x no cartão")
    assert "Cartão Roxo" in res["pending_actions"][0]["summary"]


def test_missing_account_is_returned_to_model_and_cancel(client, setup):
    fake = FakeProvider(script=[
        call("create_transaction", date=today().isoformat(), description="Padaria", amount_cents=1200,
             type="expense"),
        "Em qual conta: Conta Corrente, Cartão Roxo ou Nubank?",
    ])  # fmt: skip
    register_provider("fake", fake)
    res = chat(client, "gastei 12 na padaria")
    assert res["pending_actions"] == []
    assert res["steps"][0]["error"] is True
    assert "Pergunte ao usuário" in fake.calls[1]["messages"][-1]["content"]

    # cancel flow + conversation memory
    register_provider("fake", FakeProvider(script=[
        call("set_budget", category="Delivery", month=month_key(today()), limit_cents=50000), "Confirma?",
    ]))  # fmt: skip
    res2 = chat(client, "orçamento de delivery 500", res["conversation_id"])
    assert res2["conversation_id"] == res["conversation_id"]
    act = res2["pending_actions"][0]
    assert client.post(f"/api/assistant/actions/{act['id']}/cancel").json()["status"] == "cancelled"
    assert client.get("/api/budgets").json() == []


def test_iteration_limit(client, setup):
    register_provider("fake", FakeProvider(handler=lambda *_: call("get_summary")))
    res = chat(client, "loop")
    assert res["hit_limit"] is True
    assert "reformular" in res["reply"]
    assert len(res["steps"]) == 6


def test_goal_tools(client, setup):
    register_provider(
        "fake", FakeProvider(script=[call("create_goal", name="Viagem", target_cents=500000), "ok"])
    )
    act = chat(client, "crie uma meta viagem de 5 mil")["pending_actions"][0]
    client.post(f"/api/assistant/actions/{act['id']}/confirm")
    register_provider(
        "fake", FakeProvider(script=[call("update_goal", goal="viagem", add_cents=20000), "ok"])
    )
    act = chat(client, "guardei 200 na viagem")["pending_actions"][0]
    assert "R$ 0,00 → R$ 200,00" in act["summary"]
    client.post(f"/api/assistant/actions/{act['id']}/confirm")
    assert client.get("/api/goals").json()[0]["current_cents"] == 20000


def test_delete_transaction_tool(client, setup):
    tx = client.post("/api/transactions", json={
        "date": today().isoformat(), "description": "Cinema", "amount_cents": 5000, "type": "expense",
        "account_id": setup["checking"]["id"]}).json()  # fmt: skip
    register_provider(
        "fake", FakeProvider(script=[call("delete_transaction", transaction_id=tx["id"]), "ok"])
    )
    act = chat(client, "apaga o cinema")["pending_actions"][0]
    assert "Cinema" in act["summary"]
    client.post(f"/api/assistant/actions/{act['id']}/confirm")
    assert client.get("/api/transactions", params={"q": "Cinema"}).json()["total"] == 0
