from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session, func, select

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, AuthContext, current_auth, current_user
from app.config import get_settings
from app.db import get_session
from app.models import User, UserSession
from app.schemas.api import LoginIn, SetupIn, UserCreate, UserOut
from app.services.auth import authenticate, create_session, create_user

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(current_auth)])


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    max_age = s.session_max_age_days * 86400
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
    )
    # Readable by JS on purpose (double-submit CSRF): sent back as X-CSRF-Token.
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=max_age, httponly=False, samesite="lax", secure=s.cookie_secure
    )


@router.get("/status")
def status(request: Request, db: Session = Depends(get_session)) -> dict:
    from app.services.auth import resolve_session

    needs_setup = db.exec(select(func.count()).select_from(User)).one() == 0
    resolved = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    user = resolved[0] if resolved else None
    return {
        "needs_setup": needs_setup,
        "user": UserOut.model_validate(user, from_attributes=True) if user else None,
        "csrf_token": resolved[1].csrf_token if resolved else None,
    }


@router.post("/setup", response_model=UserOut)
def setup(data: SetupIn, response: Response, db: Session = Depends(get_session)):
    """Create the first user. Only allowed while there are no users."""
    if db.exec(select(func.count()).select_from(User)).one() > 0:
        raise HTTPException(status_code=409, detail="configuração inicial já foi feita")
    user = create_user(db, data.name, data.username, data.password)
    sess = create_session(db, user)
    _set_cookies(response, sess.token, sess.csrf_token)
    return user


@router.post("/login", response_model=UserOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_session)):
    user = authenticate(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="usuário ou senha inválidos")
    sess = create_session(db, user)
    _set_cookies(response, sess.token, sess.csrf_token)
    return user


@router.post("/logout")
def logout(
    response: Response,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_session),
) -> dict:
    sess = db.get(UserSession, auth.session.token)
    if sess:
        db.delete(sess)
        db.commit()
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return {"ok": True}


@users_router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_session)):
    return db.exec(select(User).order_by(User.id)).all()


@users_router.post("", response_model=UserOut, status_code=201)
def add_user(data: UserCreate, db: Session = Depends(get_session)):
    if db.exec(select(User).where(User.username == data.username.strip().lower())).first():
        raise HTTPException(status_code=409, detail="nome de usuário já existe")
    return create_user(db, data.name, data.username, data.password)


@users_router.delete("/{user_id}")
def remove_user(user_id: int, me: User = Depends(current_user), db: Session = Depends(get_session)):
    if user_id == me.id:
        raise HTTPException(status_code=400, detail="você não pode remover a si mesmo")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="usuário não encontrado")
    for s in db.exec(select(UserSession).where(UserSession.user_id == user_id)):
        db.delete(s)
    db.delete(user)
    db.commit()
    return {"ok": True}
