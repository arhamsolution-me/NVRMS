"""Stream tokens: short-lived, single-camera, user-bound cryptographic tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import PyJWTError

from hub_backend.config import get_settings

STREAM_TOKEN_LIFETIME_SECONDS = 60
settings = get_settings()


def create_stream_token(
    user_id: uuid.UUID,
    camera_id: uuid.UUID,
    tenant_id: uuid.UUID,
    stream_type: str = "sub",  # "main" or "sub"
    expires_in_seconds: int = STREAM_TOKEN_LIFETIME_SECONDS,
) -> str:
    """Generate short-lived cryptographic stream playback token."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "camera_id": str(camera_id),
        "tenant_id": str(tenant_id),
        "stream_type": stream_type,
        "token_type": "stream_playback",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    return jwt.encode(  # type: ignore[no-any-return]
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def verify_stream_token(token: str) -> dict[str, Any]:
    """Decode and validate stream playback token.

    Raises:
        ValueError: If token is invalid, expired, or wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except (PyJWTError, Exception) as exc:
        raise ValueError(f"Invalid or expired stream token: {exc}") from exc

    if payload.get("token_type") != "stream_playback":
        raise ValueError("Invalid token type (expected stream_playback)")

    return payload
