"""Database engine, session dependency and seed data."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app import models  # noqa: F401  (register tables)
from app.config import get_settings
from app.models import Category

DEFAULT_CATEGORIES: list[tuple[str, str, str, str]] = [
    # name, kind, icon, color
    ("Salário", "income", "💼", "#16a34a"),
    ("Freelance", "income", "🧑‍💻", "#22c55e"),
    ("Investimentos", "income", "📈", "#15803d"),
    ("Outras receitas", "income", "💰", "#4ade80"),
    ("Mercado", "expense", "🛒", "#f97316"),
    ("Restaurantes", "expense", "🍽️", "#ef4444"),
    ("Delivery", "expense", "🛵", "#dc2626"),
    ("Transporte", "expense", "🚗", "#3b82f6"),
    ("Moradia", "expense", "🏠", "#8b5cf6"),
    ("Contas e serviços", "expense", "💡", "#a855f7"),
    ("Saúde", "expense", "🩺", "#06b6d4"),
    ("Educação", "expense", "📚", "#0ea5e9"),
    ("Lazer", "expense", "🎉", "#ec4899"),
    ("Assinaturas", "expense", "📺", "#d946ef"),
    ("Compras", "expense", "🛍️", "#f59e0b"),
    ("Viagem", "expense", "✈️", "#14b8a6"),
    ("Pets", "expense", "🐾", "#a16207"),
    ("Impostos e taxas", "expense", "🧾", "#64748b"),
    ("Outros", "expense", "📦", "#94a3b8"),
]


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - driver hook
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def make_engine(url: str):
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    # timeout: wait for SQLite write locks instead of failing with "database is locked"
    return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})


engine = make_engine(get_settings().database_url)

# Every new income/expense also writes an OutboxEvent in the same transaction.
from app.services.events import register_outbox_hooks  # noqa: E402

register_outbox_hooks()


def init_db(eng=None) -> None:
    eng = eng or engine
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        seed_categories(session)


def seed_categories(session: Session) -> None:
    if session.exec(select(Category)).first():
        return
    for name, kind, icon, color in DEFAULT_CATEGORIES:
        session.add(Category(name=name, kind=kind, icon=icon, color=color))
    session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
