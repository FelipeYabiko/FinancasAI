from datetime import date

import pytest

from app.llm.providers import register_provider
from app.llm.providers.fake import FakeProvider
from app.services.assistant.tools import get_summary, query_transactions
from app.services.ledger import account_balances
from evals.common import ModelSpec
from evals.suites import agent
from evals.suites.extraction import aggregate, match, score_document


def test_match_tolerates_date_shift_and_reports_fields():
    gold = [
        {
            "date": "2026-01-05",
            "description": "UBER *TRIP",
            "amount_cents": -1000,
            "type": "expense",
        },
        {"date": "2026-01-06", "description": "PADARIA", "amount_cents": -500, "type": "expense"},
    ]
    pred = [
        {
            "date": "2026-01-06",
            "description": "Uber trip",
            "amount_cents": 1000,
            "type": "income",
        },  # sign wrong
        {"date": "2026-01-06", "description": "PADARIA", "amount_cents": -500, "type": "expense"},
        {
            "date": "2026-01-06",
            "description": "SALDO DO DIA",
            "amount_cents": 99999,
            "type": "income",
        },
    ]
    assert len(match(pred, gold)) == 2
    s = score_document(pred, gold)
    assert (s["tp"], s["fp"], s["fn"]) == (2, 1, 0)
    assert s["fields"]["amount"] == 1
    assert s["fields"]["date"] == 1
    assert s["fields"]["description"] == 2


@pytest.fixture(scope="module")
def cases():
    return agent.load_cases()


def test_agent_case_answers_are_true(cases):
    """Every number the agent is expected to say must be what the tools return."""
    db = agent.seeded_session(cases["seed"])
    s = get_summary(db, {"month": "2026-10", "category": "Delivery"})
    assert s["expense_brl"] == "R$ 123,40"
    assert get_summary(db, {"month": "2026-09"})["expense_brl"] == "R$ 1.979,90"
    t = query_transactions(
        db, {"category": "Transporte", "date_from": "2026-09-01", "date_to": "2026-10-31"}
    )
    assert t["expense_brl"] == "R$ 314,70"
    balances = account_balances(db, until=date(2026, 10, 15))
    assert 1859780 in balances.values()
    budget = get_summary(db, {"month": "2026-10"})["budgets"][0]
    assert (budget["limit_brl"], budget["spent_brl"]) == ("R$ 400,00", "R$ 123,40")  # 276,60 left


def _scripted(*outputs):
    register_provider("fake", FakeProvider(script=list(outputs)))


def test_agent_checker_scores_correct_behaviour(cases):
    by_id = {c["id"]: c for c in cases["cases"]}
    today = date.fromisoformat(cases["today"])
    spec = ModelSpec("fake", "fake")

    _scripted(
        {
            "tool_calls": [
                {
                    "name": "create_transaction",
                    "arguments": {
                        "date": "2026-10-14",
                        "description": "Mercado",
                        "amount_cents": 4500,
                        "type": "expense",
                        "account": "Nubank",
                        "category": "Mercado",
                    },
                }
            ]
        },
        "Confirma?",
    )
    r = agent.run_case(spec, by_id["expense_yesterday_card"], cases["seed"], today)
    assert r["passed"], r

    _scripted(
        {
            "tool_calls": [
                {"name": "get_summary", "arguments": {"month": "2026-10", "category": "Delivery"}}
            ]
        },
        "Você gastou R$ 123,40 com delivery.",
    )
    r = agent.run_case(spec, by_id["delivery_this_month"], cases["seed"], today)
    assert r["passed"], r

    _scripted("Em qual conta?")
    assert agent.run_case(spec, by_id["ambiguous_account"], cases["seed"], today)["passed"]

    # acting on an ambiguous request fails the case
    _scripted(
        {
            "tool_calls": [
                {
                    "name": "create_transaction",
                    "arguments": {
                        "date": "2026-10-15",
                        "description": "Farmácia",
                        "amount_cents": 5000,
                        "type": "expense",
                        "account": "Conta Corrente",
                    },
                }
            ]
        },
        "Feito",
    )
    assert not agent.run_case(spec, by_id["ambiguous_account"], cases["seed"], today)["passed"]

    _scripted(
        {"tool_calls": [{"name": "query_transactions", "arguments": {"text": "cinema"}}]},
        {"tool_calls": [{"name": "delete_transaction", "arguments": {"transaction_id": 7}}]},
        "Confirma?",
    )
    r = agent.run_case(spec, by_id["delete_cinema"], cases["seed"], today)
    assert r["passed"], r


def test_report_conclusion_prefers_cheap_model_within_tolerance():
    from evals.report import conclusion

    ext = {
        "a:big": {"f1": 0.97, "cost_per_statement_usd": 0.01, "latency_p95_ms": 9000},
        "b:small": {"f1": 0.96, "cost_per_statement_usd": 0.001, "latency_p95_ms": 3000},
        "fake:fake": {"f1": 0.99, "cost_per_statement_usd": 0.0, "latency_p95_ms": 1},
    }
    text = conclusion(ext, {}, {})
    assert "`a:big` has the best F1" in text  # fake provider is never recommended
    assert "use `b:small` by default" in text
    assert "No real LLM" in conclusion({"fake:fake": ext["fake:fake"]}, {}, {})


def test_agent_case_fails_when_turn_errors(cases):
    """Proposing the right action and then crashing on the next model call is not a pass."""
    from app.llm.types import ProviderError

    by_id = {c["id"]: c for c in cases["cases"]}
    _scripted(
        {
            "tool_calls": [
                {
                    "name": "create_transaction",
                    "arguments": {
                        "date": "2026-10-14",
                        "description": "Mercado",
                        "amount_cents": 4500,
                        "type": "expense",
                        "account": "Nubank",
                        "category": "Mercado",
                    },
                }
            ]
        },
        ProviderError("HTTP 400", 400, False),
    )
    r = agent.run_case(
        ModelSpec("fake", "fake"),
        by_id["expense_yesterday_card"],
        cases["seed"],
        date.fromisoformat(cases["today"]),
    )
    assert r["checks"]["turn_completed"] is False
    assert not r["passed"]
    assert "400" in r["error"]


def test_report_with_single_llm_does_not_pick_a_winner():
    from evals.report import conclusion

    ext = {
        "groq:x": {
            "f1": 0.9,
            "documents": 4,
            "cost_per_statement_usd": 0.001,
            "latency_p95_ms": 100,
        }
    }
    text = conclusion(ext, {}, {"groq:x": {"pass_rate": 1.0, "cases": 6}})
    assert "Only one LLM" in text
    assert "best" not in text


def test_provider_errors_are_skipped_not_scored_as_misses():
    scored = {
        "tp": 9,
        "fp": 1,
        "fn": 1,
        "fields": {"amount": 9},
        "installments": 0,
        "latency_ms": 100,
        "cost_usd": 0.001,
    }
    rate_limited = {
        "tp": 0,
        "fp": 0,
        "fn": 40,
        "fields": {},
        "installments": 0,
        "latency_ms": 0,
        "cost_usd": 0.0,
        "skipped": "quota_exhausted",
    }
    agg = aggregate([scored, rate_limited])
    assert agg["documents"] == 1
    assert agg["documents_skipped"] == 1
    assert agg["recall"] == 0.9  # the 40 rate-limited rows are not counted as misses
