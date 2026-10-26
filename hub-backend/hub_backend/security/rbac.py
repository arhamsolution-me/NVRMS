"""RBAC permission enforcement with Redis cache versioning and instant revocation."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hub_backend.db import get_db
from hub_backend.models.base import ensure_utc
from hub_backend.models.rbac import Permission, RolePermission
from hub_backend.models.user import User
from hub_backend.redis import get_redis
from hub_backend.security.tokens import TokenPayload, decode_access_token
from hub_backend.ws.events import ws_manager

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user_payload(
    request: Request,
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> TokenPayload:
    """Extract and validate the access token from Authorization header or cookie."""
    token: str | None = None
    if auth_header is not None:
        token = auth_header.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_current_user(
    payload: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Fetch the active user entity from the database."""
    user_id = uuid.UUID(payload.sub)
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.scopes), selectinload(User.role))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Check lockout
    now = datetime.now(UTC)
    locked_until_utc = ensure_utc(user.locked_until)
    if locked_until_utc and locked_until_utc > now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked due to failed login attempts",
        )

    return user


async def get_role_permissions(
    role_id: uuid.UUID,
    db: AsyncSession,
) -> set[str]:
    """Retrieve granted permissions for a role, using versioned Redis cache."""
    redis = await get_redis()
    role_str = str(role_id)
    version_key = f"role_version:{role_str}"

    version = await redis.get(version_key)
    if version is None:
        version = "1"
        await redis.set(version_key, "1")

    cache_key = f"role_perms:{role_str}:{version}"
    cached = await redis.smembers(cache_key)  # type: ignore[misc]
    if cached:
        return set(cached)

    # Cache miss: query database
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(
            RolePermission.role_id == role_id,
            RolePermission.is_granted.is_(True),
        )
    )
    result = await db.execute(stmt)
    perms = set(result.scalars().all())

    # Populate cache
    if perms:
        await redis.sadd(cache_key, *perms)  # type: ignore[misc]
        await redis.expire(cache_key, 3600)

    return perms


async def invalidate_role_cache(role_id: uuid.UUID) -> None:
    """Increment role version to immediately invalidate permission cache and notify active clients."""
    redis = await get_redis()
    role_str = str(role_id)
    version_key = f"role_version:{role_str}"
    new_version = await redis.incr(version_key)

    # Broadcast permissions_changed via WebSocket
    await ws_manager.broadcast_to_role(
        role_str,
        "permissions_changed",
        {"role_id": role_str, "version": new_version},
    )


def require_permission(permission_code: str) -> Callable[..., Any]:
    """FastAPI dependency factory enforcing a specific permission code."""

    async def dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # Superuser always bypasses checks
        if user.is_superuser:
            return user

        granted = await get_role_permissions(user.role_id, db)
        if permission_code not in granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{permission_code}' required",
            )
        return user

    return dependency
