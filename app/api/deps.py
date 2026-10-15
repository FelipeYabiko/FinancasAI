"""Shared FastAPI dependencies: DB session, auth and CSRF."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.db import get_session
from app.models import User, UserSession
from app.services.auth import resolve_session

SESSION_COOKIE = "fia_session"
CSRF_COOKIE = "fia_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class AuthContext:
    user: User
    session: UserSession


def current_auth(request: Request, db: Session = Depends(get_session)) -> AuthContext:
    resolved = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    if not resolved:
        raise HTTPException(status_code=401, detail="não autenticado")
    user, sess = resolved
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER)
        if not sent or sent != sess.csrf_token:
            raise HTTPException(status_code=403, detail="token CSRF inválido")
    return AuthContext(user=user, session=sess)


def current_user(auth: AuthContext = Depends(current_auth)) -> User:
    return auth.user
