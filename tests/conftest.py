import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db import get_session, init_db
from app.main import app


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(eng)
    return eng


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def anon_client(engine):
    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(anon_client):
    r = anon_client.post(
        "/api/auth/setup", json={"name": "Ana", "username": "ana", "password": "segredo123"}
    )
    assert r.status_code == 200, r.text
    anon_client.headers["X-CSRF-Token"] = anon_client.cookies["fia_csrf"]
    return anon_client


@pytest.fixture
def accounts(client):
    checking = client.post(
        "/api/accounts",
        json={"name": "Conta Corrente", "type": "checking", "initial_balance_cents": 100000},
    ).json()
    card = client.post(
        "/api/accounts",
        json={"name": "Cartão Roxo", "type": "credit_card", "closing_day": 25, "due_day": 5},
    ).json()
    return {"checking": checking, "card": card}


@pytest.fixture
def categories(client):
    return {c["name"]: c["id"] for c in client.get("/api/categories").json()}
