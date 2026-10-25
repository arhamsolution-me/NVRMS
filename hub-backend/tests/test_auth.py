"""Stage 1 tests: Authentication, Lockout, Refresh Rotation, /me, and TOTP."""

from __future__ import annotations

import uuid

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.rbac import Role
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User
from hub_backend.security.password import hash_password


class TestAuthentication:
    """Test login, credential verification, and account lockout."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient) -> None:
        """Super admin should log in successfully with seeded credentials."""
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "refresh_token" in res.cookies

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, client: AsyncClient) -> None:
        """Login with wrong password should return 401."""
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "WrongPassword!"},
        )
        assert res.status_code == 401
        assert "Invalid" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_unknown_email(self, client: AsyncClient) -> None:
        """Login with non-existent email should return 401."""
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@nvrsms.local", "password": "AnyPassword1!"},
        )
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_account_lockout_after_5_failures(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """After 5 consecutive failed login attempts, account must be locked for 15 minutes."""
        # Create a test user for lockout testing
        tenant_res = await db_session.execute(select(Tenant).limit(1))
        tenant = tenant_res.scalar_one()
        role_res = await db_session.execute(select(Role).limit(1))
        role = role_res.scalar_one()

        test_email = f"lockout_{uuid.uuid4().hex[:8]}@test.local"
        user = User(
            tenant_id=tenant.id,
            email=test_email,
            password_hash=hash_password("CorrectPass123!"),
            full_name="Lockout Target",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        # Fail 4 times (401)
        for _ in range(4):
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": test_email, "password": "WrongPassword!"},
            )
            assert res.status_code == 401

        # 5th failure triggers lockout (403)
        res5 = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": "WrongPassword!"},
        )
        assert res5.status_code == 403
        assert "locked" in res5.json()["detail"].lower()

        # Subsequent attempt even with CORRECT password is still locked out
        res6 = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": "CorrectPass123!"},
        )
        assert res6.status_code == 403
        assert "locked" in res6.json()["detail"].lower()


class TestTokenRotation:
    """Test rotating refresh tokens and reuse detection."""

    @pytest.mark.asyncio
    async def test_refresh_token_rotation_success(self, client: AsyncClient) -> None:
        """Calling /refresh with cookie returns new access token and rotates cookie."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        assert login_res.status_code == 200
        first_refresh = login_res.cookies.get("refresh_token")
        assert first_refresh is not None

        # Call refresh
        refresh_res = await client.post("/api/v1/auth/refresh")
        assert refresh_res.status_code == 200
        new_data = refresh_res.json()
        assert "access_token" in new_data

        second_refresh = refresh_res.cookies.get("refresh_token")
        assert second_refresh is not None
        assert second_refresh != first_refresh

    @pytest.mark.asyncio
    async def test_refresh_token_reuse_detection(self, client: AsyncClient) -> None:
        """Presenting a revoked refresh token triggers reuse detection and revokes family."""
        # 1. Login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        token_v1 = login_res.cookies.get("refresh_token")

        # 2. Legitimate refresh (token_v1 becomes revoked, token_v2 issued)
        ref_res1 = await client.post("/api/v1/auth/refresh")
        assert ref_res1.status_code == 200
        token_v2 = ref_res1.cookies.get("refresh_token")

        # 3. Attacker tries to replay token_v1
        replay_res = await client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": token_v1},
        )
        assert replay_res.status_code == 401
        assert "reuse" in replay_res.json()["detail"].lower()

        # 4. Now token_v2 should ALSO be rejected because family was revoked!
        legit_res2 = await client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": token_v2},
        )
        assert legit_res2.status_code == 401


class TestMeEndpoint:
    """Test /me profile endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, client: AsyncClient) -> None:
        """Authenticated user receives full profile with permissions."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        token = login_res.json()["access_token"]

        me_res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        data = me_res.json()
        assert data["email"] == "admin@nvrsms.local"
        assert data["is_superuser"] is True
        assert len(data["permissions"]) > 0

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, client: AsyncClient) -> None:
        """Request without token returns 401."""
        res = await client.get("/api/v1/auth/me")
        assert res.status_code == 401


class TestTOTP:
    """Test two-factor authentication setup and verification."""

    @pytest.mark.asyncio
    async def test_totp_setup_and_verification_flow(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Full 2FA flow: setup -> verify valid code -> login requires TOTP."""
        # Create a test user
        tenant_res = await db_session.execute(select(Tenant).limit(1))
        tenant = tenant_res.scalar_one()
        role_res = await db_session.execute(select(Role).limit(1))
        role = role_res.scalar_one()

        email = f"totp_user_{uuid.uuid4().hex[:8]}@test.local"
        password = "Password123!"
        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            full_name="TOTP User",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        # Login before 2FA
        login_res = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Initialize TOTP setup
        setup_res = await client.post("/api/v1/auth/totp/setup", headers=headers)
        assert setup_res.status_code == 200
        secret = setup_res.json()["secret"]
        assert len(secret) >= 16

        # Try invalid code
        bad_verify = await client.post(
            "/api/v1/auth/totp/verify",
            headers=headers,
            json={"code": "000000"},
        )
        assert bad_verify.status_code == 400

        # Generate valid TOTP code
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        good_verify = await client.post(
            "/api/v1/auth/totp/verify",
            headers=headers,
            json={"code": valid_code},
        )
        assert good_verify.status_code == 200

        # Now login without TOTP code must fail
        login_without = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_without.status_code == 401
        assert "totp" in login_without.json()["detail"].lower()

        # Login with valid TOTP code succeeds
        login_with = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "totp_code": totp.now()},
        )
        assert login_with.status_code == 200
        assert "access_token" in login_with.json()
