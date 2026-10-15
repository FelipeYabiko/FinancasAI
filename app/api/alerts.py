"""Proxy to the Java alerts-service (service-to-service call with an internal token).

The browser only talks to this app; the alerts-service stays on the internal network."""

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_auth
from app.config import get_settings

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(current_auth)])
TIMEOUT = 3.0


def _call(method: str, path: str, **kwargs) -> dict:
    s = get_settings()
    headers = {"X-Internal-Token": s.alerts_internal_token} if s.alerts_internal_token else {}
    try:
        resp = httpx.request(
            method,
            f"{s.alerts_service_url.rstrip('/')}{path}",
            headers=headers,
            timeout=TIMEOUT,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="serviço de alertas indisponível") from exc
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="alerta não encontrado")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"serviço de alertas respondeu {resp.status_code}"
        )
    return resp.json()


@router.get("")
def list_alerts(unread_only: bool = True, size: int = 10) -> dict:
    if not get_settings().alerts_service_url:
        return {"enabled": False, "items": [], "total": 0}
    data = _call("GET", "/api/alerts", params={"unreadOnly": unread_only, "size": min(size, 50)})
    return {"enabled": True, **data}


@router.patch("/{alert_id}/read")
def mark_read(alert_id: str) -> dict:
    if not get_settings().alerts_service_url:
        raise HTTPException(status_code=404, detail="serviço de alertas não configurado")
    return _call("PATCH", f"/api/alerts/{alert_id}/read")
