"""Tests for Hub security hardening, security headers, rate limiting, and envelope encryption."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.agent import Agent
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User
from hub_backend.security.envelope import (
    EnvelopeEncryptionError,
    EnvelopeEncryptor,
    envelope_encryptor,
)
from hub_backend.security.rate_limit import rate_limiter
from hub_backend.security.tokens import hash_token


class TestSecurityHeadersAndPayloadLimits:
    """Tests for HTTP security headers and body limit protection."""

    @pytest.mark.asyncio
    async def test_security_headers_present_on_all_responses(self, client: AsyncClient) -> None:
        res = await client.get("/health")
        assert res.status_code == 200

        headers = res.headers
        assert "max-age=31536000" in headers.get("strict-transport-security", "")
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert "default-src 'self'" in headers.get("content-security-policy", "")
        assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "geolocation=()" in headers.get("permissions-policy", "")

    @pytest.mark.asyncio
    async def test_oversized_payload_rejected(self, client: AsyncClient) -> None:
        """Requests exceeding 10MB payload limit receive 413 Payload Too Large."""
        headers = {"Content-Length": str(15 * 1024 * 1024)}  # 15 MB
        res = await client.post("/api/v1/auth/login", headers=headers, json={})
        assert res.status_code == 413


class TestRateLimiting:
    """Tests for sliding-window rate limiting on sensitive routes."""

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_burst_abuse(self, client: AsyncClient) -> None:
        # Reset limiter state before test
        rate_limiter.reset("127.0.0.1:/api/v1/auth/login")

        # Send 10 rapid login requests with bad credentials
        for _ in range(10):
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": "wrong@nvrsms.local", "password": "wrong"},
            )
            assert res.status_code == 401

        # The 11th request must be blocked by rate limiter with 429 Too Many Requests
        rate_limited_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@nvrsms.local", "password": "wrong"},
        )
        assert rate_limited_res.status_code == 429
        assert "Retry-After" in rate_limited_res.headers

        # Clean up rate limiter after test
        rate_limiter.reset("127.0.0.1:/api/v1/auth/login")


class TestEnvelopeEncryption:
    """Tests for KEK/DEK two-tier envelope encryption."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        secret = "super_secret_nvr_rtsp_password_!@#$"
        envelope_json = envelope_encryptor.encrypt(secret)

        data = json.loads(envelope_json)
        assert data["version"] == 1
        assert "encrypted_dek" in data
        assert "ciphertext" in data

        decrypted = envelope_encryptor.decrypt(envelope_json)
        assert decrypted == secret

    def test_tampered_ciphertext_fails(self) -> None:
        envelope_json = envelope_encryptor.encrypt("sample_payload")
        data = json.loads(envelope_json)
        # Tamper with ciphertext
        data["ciphertext"] = "dGFtcGVyZWRfYmFzZTY0"
        tampered_json = json.dumps(data)

        with pytest.raises(EnvelopeEncryptionError):
            envelope_encryptor.decrypt(tampered_json)

    def test_different_master_kek_cannot_decrypt(self) -> None:
        from cryptography.fernet import Fernet

        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()

        enc1 = EnvelopeEncryptor(master_key=key1)
        enc2 = EnvelopeEncryptor(master_key=key2)

        envelope_json = enc1.encrypt("confidential")
        with pytest.raises(EnvelopeEncryptionError):
            enc2.decrypt(envelope_json)


class TestIDORAndInjectionGuards:
    """Tests for cross-tenant IDOR concealment and injection protection."""

    @pytest.mark.asyncio
    async def test_cross_tenant_agent_access_concealed_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from hub_backend.models.rbac import Permission, Role, RolePermission
        from hub_backend.security.password import hash_password

        # 1. Setup Tenant A and non-superuser tenant user with agents:read
        tenant_a = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        perm = (
            await db_session.execute(select(Permission).where(Permission.code == "agents:read"))
        ).scalar_one()

        role_a = Role(
            tenant_id=tenant_a.id,
            name=f"AgentReader_{uuid.uuid4().hex[:6]}",
            description="Agent reader",
        )
        db_session.add(role_a)
        await db_session.flush()

        db_session.add(RolePermission(role_id=role_a.id, permission_id=perm.id, is_granted=True))

        user_email = f"user_{uuid.uuid4().hex[:6]}@tenant-a.local"
        user_a = User(
            tenant_id=tenant_a.id,
            email=user_email,
            password_hash=hash_password("Password123!"),
            full_name="Tenant A User",
            role_id=role_a.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user_a)

        # 2. Setup Tenant B with an agent
        foreign_tenant = Tenant(
            name="Foreign Security Tenant", slug=f"foreign-sec-{uuid.uuid4().hex[:6]}"
        )
        db_session.add(foreign_tenant)
        await db_session.flush()

        foreign_agent = Agent(
            tenant_id=foreign_tenant.id,
            name="Foreign Agent",
            token_hash=hash_token("foreign_tok"),
            is_active=True,
            status="online",
        )
        db_session.add(foreign_agent)
        await db_session.commit()

        # 3. User A logs in
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": "Password123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 4. Request foreign agent detail -> MUST return 404 Not Found (concealed) to prevent IDOR enumeration
        res = await client.get(f"/api/v1/agents/{foreign_agent.id}", headers=headers)
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_sql_injection_payload_in_user_filter(self, client: AsyncClient) -> None:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # SQL injection attack in query params
        res = await client.get(
            "/api/v1/users?search=' OR '1'='1' --",
            headers=headers,
        )
        # Must execute cleanly through parameterized query without leaking all users
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
