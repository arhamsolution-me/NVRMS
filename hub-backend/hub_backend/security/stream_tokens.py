"""Stream tokens: short-lived, single-camera, user-bound cryptographic tokens with jti revocation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import PyJWTError

from hub_backend.config import get_settings

STREAM_TOKEN_LIFETIME_SECONDS = 60
settings = get_settings()

# In-memory revocation set for revoked jti identifiers
_revoked_stream_tokens: set[str] = set()


def revoke_stream_token(jti: str) -> None:
    """Blacklist a stream token by its unique jti identifier."""
    _revoked_stream_tokens.add(jti)


def is_stream_token_revoked(jti: str) -> bool:
    """Check whether a stream token's jti is in the revocation blacklist."""
    return jti in _revoked_stream_tokens


def clear_revoked_stream_tokens() -> None:
    """Clear blacklist (used between test runs)."""
    _revoked_stream_tokens.clear()


def create_stream_token(
    user_id: uuid.UUID,
    camera_id: uuid.UUID,
    tenant_id: uuid.UUID,
    stream_type: str = "sub",  # "main" or "sub"
    expires_in_seconds: int = STREAM_TOKEN_LIFETIME_SECONDS,
    session_id: str | None = None,
    client_ip: str | None = None,
    jti: str | None = None,
) -> str:
    """Generate short-lived cryptographic stream playback token with jti and session binding."""
    now = datetime.now(UTC)
    token_jti = jti or str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "camera_id": str(camera_id),
        "tenant_id": str(tenant_id),
        "stream_type": stream_type,
        "token_type": "stream_playback",
        "jti": token_jti,
        "session_id": session_id or str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    if client_ip:
        payload["client_ip"] = client_ip

    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def verify_stream_token(token: str, client_ip: str | None = None) -> dict[str, Any]:
    """Decode and validate stream playback token, verifying jti revocation and client binding.

    Raises:
        ValueError: If token is invalid, expired, wrong type, or revoked.
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

    token_jti = payload.get("jti")
    if token_jti and is_stream_token_revoked(token_jti):
        raise ValueError("Stream token has been revoked")

    if client_ip and payload.get("client_ip") and payload["client_ip"] != client_ip:
        raise ValueError("Stream token client IP mismatch")

    from typing import cast

    return cast(dict[str, Any], payload)
