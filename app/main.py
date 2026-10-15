"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import accounts, auth, dashboard, planning, transactions
from app.db import init_db
from app.services.ledger import LedgerError


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="FinançasIA", lifespan=lifespan)


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
):
    app.include_router(r)
