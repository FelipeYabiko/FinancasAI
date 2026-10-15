"""Agent suite: right tool, right arguments, right final state, steps, confirmation before
writes, and asking (instead of acting) on ambiguous requests."""

from datetime import date
from pathlib import Path

import yaml
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, func, select

from app.db import init_db
from app.models import (
    Account,
    AssistantConversation,
    Budget,
    Category,
    Goal,
    PendingAction,
    Transaction,
    User,
)
from app.schemas.api import TransactionIn
from app.services import ledger
from app.services.assistant.agent import resolve_action, run_agent
from evals.common import DATASETS, CallLog, ModelSpec, md_table, p50, p95, ratio

CASES_FILE = DATASETS / "agent_cases.yaml"


def load_cases(
    subset: str | None = None, limit: int | None = None, path: Path = CASES_FILE
) -> dict:
    data = yaml.safe_load(path.read_text())
    cases = data["cases"]
    if subset == "ci":
        cases = cases[:6]
    data["cases"] = cases[:limit] if limit else cases
    return data


def seeded_session(seed: dict) -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(engine)
    db = Session(engine)
    cats = {c.name: c.id for c in db.exec(select(Category))}
    accs = {}
    for a in seed.get("accounts", []):
        acc = Account(**a)
        db.add(acc)
        db.commit()
        accs[acc.name] = acc.id
    for t in seed.get("transactions", []):
        ledger.create_transaction(
            db,
            TransactionIn(
                date=t["date"],
                description=t["description"],
                amount_cents=t["amount_cents"],
                type=t["type"],
                account_id=accs[t["account"]],
                category_id=cats.get(t.get("category")),
            ),
        )
    for b in seed.get("budgets", []):
        db.add(
            Budget(category_id=cats[b["category"]], month=b["month"], limit_cents=b["limit_cents"])
        )
    for g in seed.get("goals", []):
        db.add(Goal(**g))
    db.commit()
    return db


def _counts(db: Session) -> tuple:
    counts = [
        db.exec(select(func.count()).select_from(m)).one() for m in (Transaction, Budget, Goal)
    ]
    goals = tuple(g.current_cents for g in db.exec(select(Goal).order_by(Goal.id)))
    return (*counts, goals)


def _ref(db: Session, model, name: str) -> int | None:
    row = db.exec(select(model).where(model.name == name)).first()
    return row.id if row else None


def args_match(db: Session, expected: dict, actual: dict) -> bool:
    for key, value in expected.items():
        if key == "account":
            ok = actual.get("account_id") == _ref(db, Account, value)
        elif key in ("from_account", "to_account"):
            ok = actual.get(f"{key}_id") == _ref(db, Account, value)
        elif key == "category":
            ok = actual.get("category_id") == _ref(db, Category, value)
        elif key == "goal":
            ok = actual.get("goal_id") == _ref(db, Goal, value)
        elif key == "transaction_text":
            tx = db.get(Transaction, actual.get("transaction_id") or -1)
            ok = bool(tx) and value.lower() in tx.description.lower()
        else:
            ok = str(actual.get(key)) == str(value)
        if not ok:
            return False
    return True


def check_state(db: Session, state: dict) -> bool:
    for text, n in (state.get("transactions_with_text") or {}).items():
        rows = db.exec(select(Transaction).where(Transaction.description.contains(text))).all()
        if len(rows) != n:
            return False
    for name, cents in (state.get("goal_current") or {}).items():
        g = db.exec(select(Goal).where(Goal.name == name)).first()
        if not g or g.current_cents != cents:
            return False
    return True


def run_case(
    spec: ModelSpec, case: dict, seed: dict, today: date, prompt_version: str | None = None
) -> dict:
    db = seeded_session(seed)
    user = User(name="Eval", username="eval", password_hash="-")
    db.add(user)
    db.commit()
    conv = AssistantConversation(user_id=user.id, messages=[])
    db.add(conv)
    db.commit()
    db.refresh(conv)
    before = _counts(db)
    log = CallLog()
    reply = run_agent(
        db,
        conv,
        case["message"],
        log.client(),
        spec.provider,
        spec.model,
        prompt_version=prompt_version,
        on=today,
    )
    no_write_before_confirm = _counts(db) == before
    proposed = list(db.exec(select(PendingAction).where(PendingAction.conversation_id == conv.id)))
    called = {s.tool for s in reply.steps}
    result = {
        "id": case["id"],
        "iterations": reply.iterations,
        "cost_usd": round(log.cost, 6),
        "latency_ms": reply.latency_ms,
        "no_write_before_confirm": no_write_before_confirm,
        "proposed": [p.tool for p in proposed],
        "reply": reply.text[:300],
    }
    checks = {}
    expected = case.get("actions") or []
    if expected:
        checks["tool"] = sorted(a["tool"] for a in expected) == sorted(p.tool for p in proposed)
        remaining = list(proposed)
        args_ok = True
        for exp in expected:
            hit = next(
                (
                    p
                    for p in remaining
                    if p.tool == exp["tool"] and args_match(db, exp.get("args", {}), p.arguments)
                ),
                None,
            )
            if hit:
                remaining.remove(hit)
            else:
                args_ok = False
        checks["args"] = args_ok and checks["tool"]
        for p in proposed:
            resolve_action(db, p.id, confirm=True)
        executed = [db.get(PendingAction, p.id).status for p in proposed]
        checks["state"] = (
            checks["args"]
            and all(s == "confirmed" for s in executed)
            and check_state(db, case.get("state", {}))
        )
    if case.get("read_tools"):
        checks["tool"] = bool(called & set(case["read_tools"])) and not proposed
    if case.get("ask"):
        checks["ask"] = not proposed and "?" in reply.text
    if case.get("answer_contains"):
        checks["answer"] = any(s in reply.text for s in case["answer_contains"])
    if not expected and not case.get("read_tools") and not case.get("ask"):
        checks["no_write"] = not proposed
    checks["confirmation"] = no_write_before_confirm
    result["checks"] = checks
    result["passed"] = all(checks.values())
    db.close()
    return result


def run_model(spec: ModelSpec, data: dict, prompt_version: str | None = None) -> dict:
    today = date.fromisoformat(data["today"])
    cases = []
    for case in data["cases"]:
        try:
            r = run_case(spec, case, data["seed"], today, prompt_version)
        except Exception as exc:
            r = {
                "id": case["id"],
                "passed": False,
                "checks": {},
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "iterations": 0,
                "cost_usd": 0.0,
                "latency_ms": 0,
                "no_write_before_confirm": True,
            }
        cases.append(r)
        print(
            f"  {spec.label:45} {case['id']:30} {'PASS' if r['passed'] else 'fail'} {r.get('checks')}"
        )

    def rate(check):
        vals = [c["checks"][check] for c in cases if check in c.get("checks", {})]
        return ratio(sum(vals), len(vals))

    lat = [c["latency_ms"] for c in cases]
    return {
        "cases": len(cases),
        "pass_rate": ratio(sum(c["passed"] for c in cases), len(cases)),
        "tool_accuracy": rate("tool"),
        "args_accuracy": rate("args"),
        "state_accuracy": rate("state"),
        "answer_accuracy": rate("answer"),
        "ask_when_ambiguous": rate("ask"),
        "confirmation_before_write": ratio(
            sum(c["no_write_before_confirm"] for c in cases), len(cases)
        ),
        "avg_steps": round(sum(c["iterations"] for c in cases) / len(cases), 2) if cases else 0,
        "cost_per_case_usd": round(sum(c["cost_usd"] for c in cases) / len(cases), 6)
        if cases
        else 0,
        "latency_p50_ms": p50(lat),
        "latency_p95_ms": p95(lat),
        "per_case": cases,
    }


HEADLINE = [
    "pass_rate",
    "tool_accuracy",
    "args_accuracy",
    "state_accuracy",
    "answer_accuracy",
    "ask_when_ambiguous",
    "confirmation_before_write",
    "avg_steps",
    "cost_per_case_usd",
    "latency_p95_ms",
]


def markdown(results: dict) -> str:
    rows = [[label, *(r[m] for m in HEADLINE)] for label, r in results.items()]
    return "\n".join(["### Agent", "", md_table(["model", *HEADLINE], rows), ""])
