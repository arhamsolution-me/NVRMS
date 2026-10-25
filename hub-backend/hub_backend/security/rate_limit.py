"""Rate limiting dependency and brute-force protection."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from hub_backend.logging_config import get_logger

log = get_logger(__name__)


class SlidingWindowRateLimiter:
    """In-memory sliding-window rate limiter with per-key tracking."""

    def __init__(self) -> None:
        # key -> list of timestamp floats
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window_seconds: float) -> bool:
        """Check if request within rate limit. Returns True if allowed, False if exceeded."""
        now = time.time()
        timestamps = self._requests[key]

        # Prune timestamps older than window
        cutoff = now - window_seconds
        valid_ts = [t for t in timestamps if t > cutoff]
        self._requests[key] = valid_ts

        if len(valid_ts) >= max_requests:
            return False

        valid_ts.append(now)
        return True

    def reset(self, key: str) -> None:
        """Reset rate limit history for a key."""
        self._requests.pop(key, None)

    def reset_all(self) -> None:
        """Clear all rate limit records."""
        self._requests.clear()


rate_limiter = SlidingWindowRateLimiter()


def rate_limit(
    max_requests: int = 10,
    window_seconds: float = 60.0,
    key_func: Callable[[Request], str] | None = None,
) -> Callable[[Request], None]:
    """FastAPI dependency enforcing rate limits on endpoints."""

    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        key = key_func(request) if key_func else f"{client_ip}:{path}"

        allowed = rate_limiter.check(
            key=key, max_requests=max_requests, window_seconds=window_seconds
        )
        if not allowed:
            log.warning("rate_limit_exceeded", key=key, client_ip=client_ip, path=path)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(int(window_seconds))},
            )

    return dependency
