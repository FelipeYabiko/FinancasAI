"""Password hashing and server-side sessions."""

import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlmodel import Session, select

from app.config import get_settings
from app.models import User, UserSession


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username.strip().lower())).first()
    if user and verify_password(password, user.password_hash):
        return user
    # Constant-ish time: still run bcrypt when the user doesn't exist.
    if not user:
        verify_password(password, "$2b$12$" + "x" * 53)
    return None


def create_session(session: Session, user: User) -> UserSession:
    days = get_settings().session_max_age_days
    s = UserSession(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )
    session.add(s)
    session.commit()
    return s


def resolve_session(session: Session, token: str | None) -> tuple[User, UserSession] | None:
    if not token:
        return None
    s = session.get(UserSession, token)
    if not s:
        return None
    expires = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        session.delete(s)
        session.commit()
        return None
    user = session.get(User, s.user_id)
    return (user, s) if user else None


def create_user(session: Session, name: str, username: str, password: str) -> User:
    user = User(
        name=name.strip(), username=username.strip().lower(), password_hash=hash_password(password)
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
