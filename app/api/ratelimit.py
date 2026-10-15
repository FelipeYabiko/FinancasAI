"""In-memory sliding-window rate limit for AI endpoints (single-process app)."""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException

from app.api.deps import current_user
from app.config import get_settings
from app.models import User

_hits: dict[int, deque[float]] = defaultdict(deque)
_lock = Lock()


def ai_rate_limit(user: User = Depends(current_user)) -> User:
    limit = get_settings().ai_rate_limit_per_minute
    now = time.monotonic()
    with _lock:
        q = _hits[user.id]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status_code=429, detail="muitas requisições de IA; aguarde um minuto"
            )
        q.append(now)
    return user


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()
