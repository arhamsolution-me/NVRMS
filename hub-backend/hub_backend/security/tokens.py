"""JWT access token and cryptographic refresh token management."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from pydantic import BaseModel

from hub_backend.config import get_settings


class TokenPayload(BaseModel):
    """Decoded access token payload."""

    sub: str  # user_id
    tenant_id: str
    role_id: str
    is_superuser: bool
    exp: int
    iat: int
    token_type: str = "access"


def create_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    is_superuser: bool,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token."""
    settings = get_settings()
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role_id": str(role_id),
        "is_superuser": is_superuser,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "token_type": "access",
    }

    return jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> TokenPayload | None:
    """Decode and validate a JWT access token. Returns TokenPayload or None if invalid."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("token_type") != "access":
            return None
        return TokenPayload(**payload)
    except (JWTError, Exception):
        return None


def generate_refresh_token() -> str:
    """Generate an opaque high-entropy refresh token string."""
    return secrets.token_urlsafe(64)


def hash_token(raw_token: str) -> str:
    """Hash a raw token with SHA-256 for secure database storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
