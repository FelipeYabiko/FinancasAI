import json
from pathlib import Path

import httpx
import pytest
from sqlmodel import select

from app.models import OutboxEvent, Transaction
from app.services.events import build_event, publish_pending

CONTRACT = Path(__file__).resolve().parent.parent / "contracts" / "transaction-created.example.json"


def _shape(obj):
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in obj.items()}
    return None


def _new_expense(client, accounts, categories, **kw):
    body = {
        "date": "2026-10-14",
        "description": "ELETRO CENTER ONLINE TV",
        "amount_cents": 329900,
        "type": "expense",
        "account_id": accounts["card"]["id"],
        "category_id": categories["Compras"],
    } | kw
    return client.post("/api/transactions", json=body).json()


def test_new_transaction_writes_outbox_event_atomically(client, accounts, categories, db):
    tx = _new_expense(client, accounts, categories)
    rows = db.exec(select(OutboxEvent)).all()
    assert [(r.aggregate_id, r.type, r.published_at) for r in rows] == [
        (tx["id"], "transaction.created", None)
    ]


def test_transfers_and_backup_restore_do_not_emit(client, accounts, db):
    client.post(
        "/api/transactions/transfers",
        json={
            "date": "2026-10-14",
            "from_account_id": accounts["checking"]["id"],
            "to_account_id": accounts["card"]["id"],
            "amount_cents": 1000,
        },
    )
    assert db.exec(select(OutboxEvent)).all() == []
    client.post(
        "/api/transactions",
        json={
            "date": "2026-10-14",
            "description": "X",
            "amount_cents": 100,
            "type": "expense",
            "account_id": accounts["checking"]["id"],
        },
    )
    dump = client.get("/api/backup/json").content
    before = len(db.exec(select(OutboxEvent)).all())
    client.post("/api/backup/json", files={"file": ("b.json", dump, "application/json")})
    assert len(db.exec(select(OutboxEvent)).all()) == before


def test_payload_matches_the_shared_contract(client, accounts, categories, db):
    client.put(
        "/api/budgets",
        json={"category_id": categories["Compras"], "month": "2026-10", "limit_cents": 300000},
    )
    tx = _new_expense(client, accounts, categories)
    payload = build_event(db, db.exec(select(OutboxEvent)).one())
    assert _shape(payload) == _shape(json.loads(CONTRACT.read_text()))
    assert payload["transaction"]["amount_cents"] == -329900
    assert payload["transaction"]["id"] == tx["id"]
    assert payload["context"]["category_budget_cents"] == 300000
    assert payload["context"]["category_month_spent_cents"] == 329900


def test_publish_marks_published_and_stops_on_failure(client, accounts, categories, db):
    for _ in range(3):
        _new_expense(client, accounts, categories)
    sent = []
    calls = {"n": 0}

    def flaky(routing_key, body, message_id):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("broker nacked")
        sent.append((routing_key, json.loads(body)["event_id"], message_id))

    assert publish_pending(db, flaky) == 1
    rows = db.exec(select(OutboxEvent).order_by(OutboxEvent.id)).all()
    assert rows[0].published_at is not None
    assert rows[1].published_at is None and rows[1].attempts == 1 and "nacked" in rows[1].last_error
    assert sent[0][1] == sent[0][2] == rows[0].event_id  # message_id = event_id (idempotency key)
    # next run resumes in order
    assert publish_pending(db, lambda *a: None) == 2


def test_deleted_transaction_is_skipped(client, accounts, categories, db):
    tx = _new_expense(client, accounts, categories)
    client.delete(f"/api/transactions/{tx['id']}")
    assert publish_pending(db, lambda *a: pytest.fail("should not publish")) == 1
    assert db.get(Transaction, tx["id"]) is None


# ---------- alerts proxy ----------
def test_alerts_disabled_without_service(client):
    assert client.get("/api/alerts").json() == {"enabled": False, "items": [], "total": 0}


def test_alerts_proxy_forwards_with_internal_token(client, monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "alerts_service_url", "http://alerts:8081")
    monkeypatch.setattr(s, "alerts_internal_token", "tok")
    seen = {}

    def fake_request(method, url, headers=None, timeout=None, **kw):
        seen.update(method=method, url=url, headers=headers, params=kw.get("params"))
        return httpx.Response(
            200, json={"items": [{"id": "a1", "title": "Gasto alto"}], "total": 1}
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    res = client.get("/api/alerts").json()
    assert res["enabled"] is True and res["items"][0]["id"] == "a1"
    assert seen["url"] == "http://alerts:8081/api/alerts"
    assert seen["headers"] == {"X-Internal-Token": "tok"}

    def down(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "request", down)
    assert client.get("/api/alerts").status_code == 502


def test_context_reflects_state_at_creation_not_at_publish(client, accounts, categories, db):
    """Two purchases before the relay runs: the first must still be the one that crossed the budget."""
    client.put(
        "/api/budgets",
        json={"category_id": categories["Compras"], "month": "2026-10", "limit_cents": 300000},
    )
    _new_expense(client, accounts, categories)
    _new_expense(client, accounts, categories)
    first, second = db.exec(select(OutboxEvent).order_by(OutboxEvent.id)).all()
    assert build_event(db, first)["context"]["category_month_spent_cents"] == 329900
    assert build_event(db, second)["context"]["category_month_spent_cents"] == 659800
