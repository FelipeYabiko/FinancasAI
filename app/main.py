"""FastAPI application entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="FinançasIA")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
