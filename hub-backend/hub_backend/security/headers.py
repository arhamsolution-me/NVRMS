"""Security headers and request boundary middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

DEFAULT_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces defense-in-depth HTTP security headers and request payload size limits."""

    def __init__(
        self,
        app,  # type: ignore[no-untyped-def]
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Check payload size limit
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > self.max_body_bytes:
                    return Response(
                        content='{"detail": "Request payload too large"}',
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        media_type="application/json",
                    )
            except ValueError:
                pass

        response = await call_next(request)

        # Apply security headers
        headers = response.headers
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; object-src 'none'"
        )
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

        return response
