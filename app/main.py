"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    accounts,
    ai,
    alerts,
    assistant,
    auth,
    dashboard,
    imports,
    insights,
    planning,
    transactions,
)
from app.config import BASE_DIR, get_settings
from app.db import init_db
from app.services.ledger import LedgerError


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings = get_settings()
    relay = None
    if settings.rabbitmq_url:
        from app.db import engine
        from app.services.events import OutboxRelay

        relay = OutboxRelay(engine, settings.rabbitmq_url, settings.events_exchange)
        relay.start()
    yield
    if relay:
        relay.stop()


app = FastAPI(title="FinançasIA", lifespan=lifespan)
STATIC_DIR = BASE_DIR / "app" / "static"

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(LedgerError)
async def ledger_error(_: Request, exc: LedgerError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


for r in (
    auth.router,
    auth.users_router,
    accounts.router,
    transactions.router,
    planning.router,
    dashboard.router,
    ai.router,
    imports.router,
    assistant.router,
    insights.router,
    alerts.router,
):
    app.include_router(r)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
