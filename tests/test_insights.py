from datetime import date

from app.domain.insights import (
    detect_anomalies,
    detect_subscriptions,
    forecast_balance,
    project_budget,
)
from app.domain.normalize import normalize_description
from app.llm.providers import register_provider
from app.llm.providers.fake import FakeProvider


class T:
    def __init__(self, d, amount, desc, type_="expense", cat=None):
        self.date = d
        self.amount_cents = amount
        self.description_normalized = normalize_description(desc)
        self.type = type_
        self.category_id = cat


def test_subscriptions_detected():
    on = date(2026, 10, 15)
    txs = [T(date(2026, m, 10), -5590, "NETFLIX.COM") for m in (6, 7, 8, 9, 10)]
    txs += [T(date(2026, m, 3), -2190 if m != 9 else -2290, "SPOTIFY BRASIL") for m in (7, 8, 9)]
    # irregular merchant: same amount but not monthly
    txs += [T(date(2026, 10, d), -1500, "PADARIA") for d in (1, 3, 9)]
    txs += [T(date(2026, m, 5), -4000, "UBER *TRIP") for m in (8, 9, 10)]
    txs[-1].amount_cents = -12000  # varying amounts → not a subscription
    # stopped subscription (last charge long ago)
    txs += [T(date(2026, m, 1), -3000, "ACADEMIA") for m in (3, 4, 5)]
    subs = detect_subscriptions(txs, on)
    assert [s.merchant for s in subs] == ["netflix com", "spotify brasil"]
    assert subs[0].amount_cents == 5590
    assert subs[0].next_expected == date(2026, 11, 9)


def test_anomalies_vs_3_month_average():
    spend = {
        1: [10000, 12000, 11000, 20000],
        2: [10000, 10000, 10000, 12000],
        3: [0, 0, 0, 9000],
        4: [2000, 2000, 2000, 5000],
    }
    out = detect_anomalies(spend)
    assert [a.category_id for a in out] == [1]  # 2: +20% only; 3: no history; 4: < R$ 50 delta
    assert out[0].average_cents == 11000
    assert out[0].change_pct == 81.8


def test_budget_projection():
    p = project_budget(1, spent=30000, limit=60000, on=date(2026, 10, 10))
    assert p.projected_cents == 93000
    assert p.exceeds_on == date(2026, 10, 20)
    ok = project_budget(1, spent=10000, limit=60000, on=date(2026, 10, 10))
    assert ok.exceeds_on is None
    over = project_budget(1, spent=70000, limit=60000, on=date(2026, 10, 10))
    assert over.exceeds_on == date(2026, 10, 10)


def test_forecast_balance():
    f = forecast_balance(100000, [(date(2026, 10, 20), -180000), (date(2026, 10, 25), 500000)], [-5000], [120000],
                         date(2026, 10, 31))  # fmt: skip
    assert f.projected_cents == 100000 + 500000 - 180000 - 5000 - 120000


def test_insights_api_with_and_without_llm(client, accounts, categories):
    acc = accounts["checking"]["id"]
    from app.domain.dates import add_months, today

    t = today()
    for i in range(4):
        d = add_months(t, -i).replace(day=min(t.day, 28))
        client.post(
            "/api/transactions",
            json={
                "date": d.isoformat(),
                "description": "NETFLIX.COM",
                "amount_cents": 5590,
                "type": "expense",
                "account_id": acc,
                "category_id": categories["Assinaturas"],
            },
        )
    client.put(
        "/api/budgets",
        json={
            "category_id": categories["Assinaturas"],
            "month": t.isoformat()[:7],
            "limit_cents": 1000,
        },
    )
    items = client.get("/api/insights").json()["items"]
    kinds = {i["kind"] for i in items}
    assert {"subscriptions", "budget", "forecast"} <= kinds
    subs = next(i for i in items if i["kind"] == "subscriptions")
    assert subs["data"]["monthly_total"] == "R$ 55,90"

    # narration: the LLM only rewrites text; numbers stay the deterministic ones
    client.put(
        "/api/ai/settings",
        json={
            f: {"provider": "fake", "model": "fake"}
            for f in ("extraction", "categorization", "assistant", "insights")
        },
    )
    register_provider(
        "fake",
        FakeProvider(
            handler=lambda msgs, tools, schema: {
                "items": [{"title": f"T{i}", "body": "texto"} for i in range(len(items))]
            }
        ),
    )
    res = client.post("/api/insights/narrate").json()
    assert res["meta"]["llm"] is True
    assert res["items"][0]["title"] == "T0"
    assert res["items"][0]["data"] == items[0]["data"]
    # wrong number of items → falls back to deterministic texts
    register_provider(
        "fake", FakeProvider(handler=lambda *_: {"items": [{"title": "x", "body": "y"}]})
    )
    res = client.post("/api/insights/narrate").json()
    assert res["meta"]["llm"] is False
    assert res["items"][0]["title"] == items[0]["title"]
