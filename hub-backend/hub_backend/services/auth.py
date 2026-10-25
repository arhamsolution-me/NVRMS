"""Authentication service: login, lockout, token rotation, and super-admin protection."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hub_backend.config import get_settings
from hub_backend.models.base import ensure_utc
from hub_backend.models.user import RefreshToken, User
from hub_backend.security.password import verify_password
from hub_backend.security.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_token,
)
from hub_backend.security.totp import verify_totp_code
from hub_backend.services.audit import record_audit_log

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    totp_code: str | None = None,
    request: Request | None = None,
) -> tuple[str, str, User]:
    """Authenticate credentials, check lockout, handle TOTP, and issue access/refresh tokens."""
    settings = get_settings()
    stmt = (
        select(User)
        .where(User.email == email.strip().lower())
        .options(selectinload(User.scopes), selectinload(User.role))
    )
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        from hub_backend.security.password import dummy_verify

        dummy_verify(password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Check lockout status
    now = datetime.now(UTC)
    locked_until_utc = ensure_utc(user.locked_until)
    if locked_until_utc and locked_until_utc > now:
        remaining = int((locked_until_utc - now).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is locked. Try again in {remaining} minutes.",
        )

    # Verify password
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            await record_audit_log(
                db=db,
                action="AUTH_LOCKOUT",
                resource_type="user",
                resource_id=user.id,
                tenant_id=user.tenant_id,
                user_id=user.id,
                details={"reason": "Excessive failed password attempts"},
                request=request,
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.",
            )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify TOTP if enabled
    if user.totp_enabled and (
        not totp_code or not user.totp_secret or not verify_totp_code(user.totp_secret, totp_code)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid 2FA/TOTP code required",
        )

    # Login successful: reset lockout counters
    user.failed_login_attempts = 0
    user.locked_until = None

    # Issue access token
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role_id=user.role_id,
        is_superuser=user.is_superuser,
    )

    # Issue rotating refresh token
    raw_refresh = generate_refresh_token()
    token_rec = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        family_id=uuid.uuid4(),
        is_revoked=False,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(token_rec)

    await record_audit_log(
        db=db,
        action="AUTH_LOGIN",
        resource_type="user",
        resource_id=user.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        request=request,
    )
    await db.commit()

    return access_token, raw_refresh, user


async def rotate_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
    request: Request | None = None,
) -> tuple[str, str, User]:
    """Rotate a refresh token, detecting reuse and revoking the family on violation."""
    settings = get_settings()
    now = datetime.now(UTC)
    hashed = hash_token(raw_refresh_token)

    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == hashed)
        .options(selectinload(RefreshToken.user).selectinload(User.role))
    )
    res = await db.execute(stmt)
    token_rec = res.scalar_one_or_none()

    if not token_rec or ensure_utc(token_rec.expires_at) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = token_rec.user
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or removed",
        )

    # Reuse detection: if a revoked token is presented, compromise is assumed!
    if token_rec.is_revoked:
        # Revoke the entire family
        stmt_family = select(RefreshToken).where(RefreshToken.family_id == token_rec.family_id)
        fam_res = await db.execute(stmt_family)
        for t in fam_res.scalars().all():
            t.is_revoked = True

        await record_audit_log(
            db=db,
            action="AUTH_TOKEN_REUSE_DETECTED",
            resource_type="refresh_token",
            resource_id=token_rec.id,
            tenant_id=user.tenant_id,
            user_id=user.id,
            details={"family_id": str(token_rec.family_id)},
            request=request,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. Session invalidated.",
        )

    # Invalidate current token
    token_rec.is_revoked = True

    # Issue new token in same family
    new_raw = generate_refresh_token()
    new_rec = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_raw),
        family_id=token_rec.family_id,
        is_revoked=False,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_rec)

    new_access = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role_id=user.role_id,
        is_superuser=user.is_superuser,
    )
    await db.commit()

    return new_access, new_raw, user


async def check_last_superadmin_protection(
    db: AsyncSession,
    target_user: User,
    demote_or_deactivate: bool = False,
) -> None:
    """Ensure that the last active super-admin cannot be deleted, deactivated, or demoted."""
    if not target_user.is_superuser:
        return

    stmt = select(func.count(User.id)).where(
        User.is_superuser.is_(True),
        User.is_active.is_(True),
    )
    res = await db.execute(stmt)
    count = res.scalar() or 0

    if count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action prohibited: Cannot delete, deactivate, or demote the last remaining Super Admin.",
        )
