"""Authentication endpoints: login, token refresh, logout, /me, and TOTP."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.config import get_settings
from hub_backend.db import get_db
from hub_backend.models.user import User
from hub_backend.schemas.auth import (
    LoginRequest,
    MeResponse,
    TokenResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    UserScopeSchema,
)
from hub_backend.security.rate_limit import rate_limit
from hub_backend.security.rbac import get_current_user, get_role_permissions
from hub_backend.security.totp import generate_totp_secret, get_totp_uri, verify_totp_code
from hub_backend.services.audit import record_audit_log
from hub_backend.services.auth import authenticate_user, rotate_refresh_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user, set secure HTTP-only refresh cookie, and return access token."""
    access_token, raw_refresh, user = await authenticate_user(
        db=db,
        email=req.email,
        password=req.password,
        totp_code=req.totp_code,
        request=request,
    )

    # Set secure HTTP-only cookie for rotating refresh token
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )
    # Also set access_token cookie for browser clients
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and get new access token",
)
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Rotate the refresh token and return a new access token."""
    # Allow fallback from body if cookie not present
    token_to_rotate = refresh_token
    if not token_to_rotate:
        body = (
            await request.json()
            if request.headers.get("content-type") == "application/json"
            else {}
        )
        token_to_rotate = body.get("refresh_token")

    if not token_to_rotate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )

    access_token, new_raw_refresh, user = await rotate_refresh_token(
        db=db,
        raw_refresh_token=token_to_rotate,
        request=request,
    )

    response.set_cookie(
        key="refresh_token",
        value=new_raw_refresh,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out and clear session cookies"
)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Clear cookies and log the logout event."""
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    response.delete_cookie("access_token")
    await record_audit_log(
        db=db,
        action="AUTH_LOGOUT",
        resource_type="user",
        resource_id=current_user.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()


@router.get("/me", response_model=MeResponse, summary="Get current user profile and permissions")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Return profile, active role, scopes, and granted permissions for the authenticated user."""
    perms: set[str]
    if current_user.is_superuser:
        perms = {"*"}
    else:
        perms = await get_role_permissions(current_user.role_id, db)

    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        tenant_id=current_user.tenant_id,
        role_id=current_user.role_id,
        role_name=current_user.role.name if current_user.role else "Unknown",
        is_superuser=current_user.is_superuser,
        totp_enabled=current_user.totp_enabled,
        scopes=[UserScopeSchema.model_validate(s) for s in current_user.scopes],
        permissions=sorted(perms),
    )


@router.post(
    "/totp/setup", response_model=TOTPSetupResponse, summary="Initialize TOTP two-factor setup"
)
async def totp_setup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TOTPSetupResponse:
    """Generate a new TOTP secret and provisioning URI."""
    secret = generate_totp_secret()
    current_user.totp_secret = secret
    await db.commit()

    uri = get_totp_uri(secret, email=current_user.email)
    return TOTPSetupResponse(secret=secret, provisioning_uri=uri)


@router.post(
    "/totp/verify",
    status_code=status.HTTP_200_OK,
    summary="Verify code and enable 2FA",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
)
async def totp_verify(
    req: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Verify code using stored temporary secret and activate 2FA."""
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP setup not initialized",
        )

    if not verify_totp_code(current_user.totp_secret, req.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code",
        )

    current_user.totp_enabled = True
    await record_audit_log(
        db=db,
        action="TOTP_ENABLED",
        resource_type="user",
        resource_id=current_user.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()

    return {"status": "ok", "message": "Two-factor authentication enabled successfully"}
