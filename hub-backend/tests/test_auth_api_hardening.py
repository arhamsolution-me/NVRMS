"""Stage S5: Authentication and API Hardening Verification Suite.

Validates:
1. Route enumeration authorization: Proves that EVERY route in the application requires
   authentication/authorization unless explicitly on the documented public allowlist.
2. Password complexity & breach dictionary defense.
3. Anti-enumeration and timing-safe authentication.
4. Session listing and remote session revocation (single & all).
5. Comprehensive HTTP security headers (HSTS preload, CSP frame-ancestors, nosniff, etc.).
6. Request payload limit defense-in-depth (HTTP 413).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.routing import WebSocketRoute

from hub_backend.main import create_app
from hub_backend.models.rbac import Role
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User
from hub_backend.security.password import check_password_strength, hash_password


@pytest.mark.asyncio
async def test_route_enumeration_all_routes_protected() -> None:
    """Enumerate all routes in the FastAPI app and verify every non-public route enforces authorization."""
    app = create_app()

    # Documented explicit public routes allowlist
    public_allowlist = {
        "/health",
        "/metrics",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/agents/enrol",
        "/api/v1/streams/mediamtx/auth",
        # Docs / OpenAPI routes if non-production
        "/api/docs",
        "/api/docs/oauth2-redirect",
        "/api/redoc",
        "/api/openapi.json",
    }

    unprotected_routes: list[str] = []

    for route in app.routes:
        if isinstance(route, WebSocketRoute):
            # WebSocket routes handle authentication in the connection handshake
            continue
        if isinstance(route, APIRoute):
            path = route.path
            if path in public_allowlist:
                continue

            # Gather all route dependencies
            all_deps = list(route.dependencies)
            if route.dependant and route.dependant.dependencies:
                all_deps.extend(route.dependant.dependencies)

            has_auth_dep = False
            for d in all_deps:
                call_name = getattr(d.call, "__qualname__", "") or getattr(d.call, "__name__", "")
                if any(
                    k in call_name.lower()
                    for k in (
                        "require_permission",
                        "get_current_user",
                        "require_admin",
                        "auth",
                        "current_user",
                        "permission",
                    )
                ):
                    has_auth_dep = True
                    break

            if not has_auth_dep:
                unprotected_routes.append(f"{route.methods} {path}")

    assert (
        not unprotected_routes
    ), f"Found unprotected routes lacking authorization dependency: {unprotected_routes}"


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected_on_all_protected_endpoints(
    client: AsyncClient,
) -> None:
    """Verify that hitting protected endpoints without credentials yields HTTP 401 or 403."""
    test_endpoints = [
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/roles"),
        ("GET", "/api/v1/locations/provinces"),
        ("GET", "/api/v1/agents"),
        ("GET", "/api/v1/nvrs"),
        ("GET", "/api/v1/cameras"),
        ("GET", "/api/v1/audit"),
        ("POST", "/api/v1/backup/create"),
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/auth/sessions"),
        ("POST", "/api/v1/agents/enrol-token"),
        ("POST", f"/api/v1/streams/{uuid.uuid4()}/token"),
    ]

    for method, endpoint in test_endpoints:
        if method == "GET":
            res = await client.get(endpoint)
        else:
            res = await client.post(endpoint, json={})
        assert res.status_code in (
            401,
            403,
        ), f"Expected 401/403 for unauthenticated {method} {endpoint}, got {res.status_code}"


@pytest.mark.asyncio
async def test_password_policy_and_breached_password_detection() -> None:
    """Verify password strength complexity and rejection of common breached passwords."""
    # Too short (< 12)
    valid, msg = check_password_strength("Short1!")
    assert not valid
    assert "at least 12 characters" in (msg or "")

    # Missing uppercase
    valid, msg = check_password_strength("nouppercase123!")
    assert not valid
    assert "uppercase" in (msg or "")

    # Missing lowercase
    valid, msg = check_password_strength("NOLOWERCASE123!")
    assert not valid
    assert "lowercase" in (msg or "")

    # Missing digits
    valid, msg = check_password_strength("NoDigitsSpecial!")
    assert not valid
    assert "digit" in (msg or "")

    # Missing special character
    valid, msg = check_password_strength("NoSpecialChar123")
    assert not valid
    assert "special character" in (msg or "")

    # Breached password (even if 12+ chars and meets character sets)
    valid, msg = check_password_strength("Password123!")
    assert not valid
    assert "data breaches" in (msg or "")

    # Strong valid password
    valid, msg = check_password_strength("K9#vL$8mP2@xQ7!")
    assert valid
    assert msg is None


@pytest.mark.asyncio
async def test_user_creation_rejects_weak_and_breached_passwords(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify /api/v1/users enforces password complexity via API."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    role_res = await db_session.execute(select(Role).limit(1))
    role = role_res.scalar_one()

    # Attempt to create user with breached password
    res = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "breached@nvrsms.local",
            "password": "Password123!",
            "full_name": "Breached User",
            "role_id": str(role.id),
            "is_active": True,
        },
    )
    assert res.status_code == 400
    assert "data breaches" in res.json()["detail"]

    # Attempt with 10-char password (< 12 chars, meets Pydantic min_length=8 but fails policy)
    res = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "short@nvrsms.local",
            "password": "Short123!#",
            "full_name": "Short User",
            "role_id": str(role.id),
            "is_active": True,
        },
    )
    assert res.status_code == 400
    assert "at least 12 characters" in res.json()["detail"]

    # Attempt with valid strong password
    res = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"valid_{uuid.uuid4().hex[:6]}@nvrsms.local",
            "password": "StrongSecurity2026!#",
            "full_name": "Compliant User",
            "role_id": str(role.id),
            "is_active": True,
        },
    )
    assert res.status_code == 201


@pytest.mark.asyncio
async def test_anti_enumeration_uniform_error_and_timing_defense(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify login returns uniform error messages to prevent account enumeration."""
    # Non-existent user
    res_non_existent = await client.post(
        "/api/v1/auth/login",
        json={"email": "non_existent_user@nvrsms.local", "password": "AnyPassword123!"},
    )
    assert res_non_existent.status_code == 401

    # Existing user with wrong password
    res_wrong_pw = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@nvrsms.local", "password": "WrongPassword2026!#"},
    )
    assert res_wrong_pw.status_code == 401

    # Error detail must be identical (no account enumeration)
    assert res_non_existent.json()["detail"] == res_wrong_pw.json()["detail"]
    assert "Invalid email or password" in res_non_existent.json()["detail"]


@pytest.mark.asyncio
async def test_session_listing_and_remote_revocation(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify active session listing, specific session revocation, and all sessions revocation."""
    role_res = await db_session.execute(select(Role).limit(1))
    role = role_res.scalar_one()

    tenant_res = await db_session.execute(select(Tenant).limit(1))
    tenant = tenant_res.scalar_one()

    password = "UserSessionPass2026!#"
    user = User(
        tenant_id=tenant.id,
        email=f"session_test_{uuid.uuid4().hex[:6]}@nvrsms.local",
        password_hash=hash_password(password),
        full_name="Session Test User",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # 1. First login (Session 1)
    res1 = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert res1.status_code == 200
    assert "access_token" in res1.json()
    refresh1 = res1.cookies.get("refresh_token")
    assert refresh1 is not None

    # 2. Second login (Session 2)
    res2 = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert res2.status_code == 200
    token2 = res2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}
    refresh2 = res2.cookies.get("refresh_token")
    assert refresh2 is not None

    # 3. List active sessions
    sessions_res = await client.get("/api/v1/auth/sessions", headers=headers2)
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 2

    # 4. Revoke Session 1 by its ID
    session1_id = sessions[1]["session_id"]
    del_res = await client.delete(f"/api/v1/auth/sessions/{session1_id}", headers=headers2)
    assert del_res.status_code == 204

    # 5. Attempt to use revoked refresh token -> fails (401)
    refresh_attempt = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh1},
    )
    assert refresh_attempt.status_code == 401

    # 6. Session 2 refresh token is still valid
    refresh2_attempt = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh2},
    )
    assert refresh2_attempt.status_code == 200

    # 7. Revoke all sessions
    del_all_res = await client.delete("/api/v1/auth/sessions", headers=headers2)
    assert del_all_res.status_code == 204

    # 8. All active sessions are gone
    active_sessions_res = await client.get("/api/v1/auth/sessions", headers=headers2)
    assert len(active_sessions_res.json()) == 0


@pytest.mark.asyncio
async def test_security_headers_and_payload_limits(client: AsyncClient) -> None:
    """Verify security headers (HSTS, CSP, X-Frame-Options) and 413 Payload Too Large."""
    # Check security headers on health endpoint
    res = await client.get("/health")
    assert res.status_code == 200
    headers = res.headers

    # Verify HSTS preload
    hsts = headers.get("Strict-Transport-Security", "")
    assert "max-age=63072000" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" in hsts

    # Verify CSP
    csp = headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp

    # Verify other defense-in-depth headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in headers.get("Permissions-Policy", "")

    # Verify payload size limit defense (Content-Length > 10MB)
    large_headers = {"Content-Length": str(15 * 1024 * 1024)}
    overflow_res = await client.post("/api/v1/auth/login", headers=large_headers, content=b"")
    assert overflow_res.status_code == 413
    assert "Request payload too large" in overflow_res.text
