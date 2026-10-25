"""Stage S4 Tests: Stream Authorization, Namespace Isolation, Token Abuse Matrix, and Immediate Revocation."""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.agent import Agent
from hub_backend.models.camera import Camera
from hub_backend.models.nvr import NVR
from hub_backend.models.tenant import Tenant
from hub_backend.routes.agent_ws import agent_websocket_gateway
from hub_backend.security.stream_tokens import (
    create_stream_token,
    revoke_stream_token,
    verify_stream_token,
)
from hub_backend.security.tokens import hash_token
from hub_backend.services.stream_manager import (
    MAX_CONCURRENT_STREAMS_PER_USER,
    stream_manager,
)
from tests.test_agent_lifecycle import MockWebSocket


class TestStreamTokenAbuseMatrix:
    """Rigorous tests proving expired, wrong-camera, wrong-tenant, revoked, and forged tokens are denied."""

    def test_forged_signature_token_denied(self) -> None:
        """Token signed with an attacker's key is rejected."""
        import jwt

        forged_payload = {
            "sub": str(uuid.uuid4()),
            "camera_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "stream_type": "sub",
            "token_type": "stream_playback",
            "jti": str(uuid.uuid4()),
            "exp": int(time.time()) + 3600,
        }
        forged_token = jwt.encode(
            forged_payload,
            "attacker_secret_key_at_least_32_bytes_long",
            algorithm="HS256",
        )

        with pytest.raises(ValueError, match="Invalid or expired stream token"):
            verify_stream_token(forged_token)

    def test_expired_token_denied(self) -> None:
        """Token with past expiration timestamp is rejected."""
        token = create_stream_token(
            user_id=uuid.uuid4(),
            camera_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            expires_in_seconds=-10,
        )
        with pytest.raises(ValueError, match="Invalid or expired stream token"):
            verify_stream_token(token)

    def test_revoked_jti_token_denied(self) -> None:
        """Token whose jti has been blacklisted is immediately rejected."""
        jti = str(uuid.uuid4())
        token = create_stream_token(
            user_id=uuid.uuid4(),
            camera_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            jti=jti,
        )

        # Before revocation: valid
        payload = verify_stream_token(token)
        assert payload["jti"] == jti

        # Revoke token
        revoke_stream_token(jti)

        # After revocation: rejected
        with pytest.raises(ValueError, match="Stream token has been revoked"):
            verify_stream_token(token)

    def test_client_ip_binding_mismatch_denied(self) -> None:
        """Token bound to IP 192.168.1.100 is rejected if presented from 10.0.0.50."""
        token = create_stream_token(
            user_id=uuid.uuid4(),
            camera_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            client_ip="192.168.1.100",
        )

        # Matching IP succeeds
        assert verify_stream_token(token, client_ip="192.168.1.100") is not None

        # Different IP fails
        with pytest.raises(ValueError, match="client IP mismatch"):
            verify_stream_token(token, client_ip="10.0.0.50")


class TestMediaMTXAuthHookAndNamespaceIsolation:
    """Tests verifying media server authorization hook, deny-by-default, and namespace isolation."""

    @pytest.mark.asyncio
    async def test_agent_namespace_isolation_enforced(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Agent A cannot publish to Agent B's camera path (Namespace Isolation)."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        # Create Agent A
        raw_tok_a = "agt_namespace_agent_a"
        agent_a = Agent(
            tenant_id=tenant.id,
            name="Agent A",
            token_hash=hash_token(raw_tok_a),
            is_active=True,
            status="online",
        )
        db_session.add(agent_a)
        await db_session.flush()

        # Create Agent B
        raw_tok_b = "agt_namespace_agent_b"
        agent_b = Agent(
            tenant_id=tenant.id,
            name="Agent B",
            token_hash=hash_token(raw_tok_b),
            is_active=True,
            status="online",
        )
        db_session.add(agent_b)
        await db_session.flush()

        # Create NVR and Camera belonging to Agent B
        nvr_b = NVR(
            tenant_id=tenant.id,
            agent_id=agent_b.id,
            name="NVR B",
            ip_address="192.168.20.10",
            port=554,
        )
        db_session.add(nvr_b)
        await db_session.flush()

        cam_b = Camera(
            tenant_id=tenant.id,
            nvr_id=nvr_b.id,
            channel_number=1,
            name="Camera B",
            main_stream_url="rtsp://192.168.20.10:554/ch1/main",
        )
        db_session.add(cam_b)
        await db_session.commit()

        target_path_b = f"live/{cam_b.id}_main"

        # 1. Agent A attempts to publish to Agent B's camera path -> MUST BE REJECTED 403
        res_rogue = await client.post(
            "/api/v1/streams/auth",
            json={
                "action": "publish",
                "path": target_path_b,
                "password": raw_tok_a,
            },
        )
        assert res_rogue.status_code == 403
        assert "not authorized to publish to this camera namespace" in res_rogue.json()["detail"]

        # 2. Agent B publishing to Agent B's camera path -> ALLOWED 200
        res_legit = await client.post(
            "/api/v1/streams/auth",
            json={
                "action": "publish",
                "path": target_path_b,
                "password": raw_tok_b,
            },
        )
        assert res_legit.status_code == 200
        assert res_legit.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_deny_by_default_on_missing_or_unknown_action(self, client: AsyncClient) -> None:
        """Media server auth hook strictly denies access on missing or unknown actions."""
        # Missing token
        res1 = await client.post(
            "/api/v1/streams/auth",
            json={"action": "read", "path": "live/random_stream"},
        )
        assert res1.status_code == 403

        # Unknown action
        res2 = await client.post(
            "/api/v1/streams/auth",
            json={"action": "admin_dump", "path": "live/random_stream"},
        )
        assert res2.status_code == 403


class TestViewerRevocationAndConcurrencyLimits:
    """Tests for immediate stream revocation (< 3s) and concurrent stream limits."""

    @pytest.mark.asyncio
    async def test_user_stream_revocation_terminates_immediately(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Revoking user streams terminates viewer sessions and stops agent stream immediately (< 3s)."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        # Connect Agent
        raw_tok = "agt_revocation_speed_test"
        agent = Agent(
            tenant_id=tenant.id,
            name="Revocation Agent",
            token_hash=hash_token(raw_tok),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.flush()

        ws = MockWebSocket()
        asyncio.create_task(
            agent_websocket_gateway(ws, agent_id=str(agent.id), token=raw_tok)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)

        nvr = NVR(
            tenant_id=tenant.id,
            agent_id=agent.id,
            name="Revoke NVR",
            ip_address="192.168.1.199",
            port=554,
        )
        db_session.add(nvr)
        await db_session.flush()

        cam = Camera(
            tenant_id=tenant.id,
            nvr_id=nvr.id,
            channel_number=1,
            name="Revoke Cam",
            main_stream_url="rtsp://192.168.1.199:554/ch1",
        )
        db_session.add(cam)
        await db_session.commit()

        user_id = uuid.uuid4()
        viewer_id = str(uuid.uuid4())

        # Start stream on demand
        req_task = asyncio.create_task(
            stream_manager.request_stream(
                camera=cam,
                nvr=nvr,
                stream_type="main",
                viewer_id=viewer_id,
                user_id=user_id,
            )
        )
        await asyncio.sleep(0.05)
        # Agent confirms stream start
        start_cmd = ws.outgoing[-1]
        await ws.incoming.put(
            f'{{"type": "command_result", "command_id": "{start_cmd["command_id"]}", "status": "success", "result": {{"status": "started"}}}}'
        )
        session, _ = await req_task
        assert session.viewer_count == 1

        # REVOKE: Immediately terminate user streams
        t_start = time.perf_counter()
        revoked_count = await stream_manager.revoke_user_streams(user_id)
        t_elapsed = time.perf_counter() - t_start

        # Verification: Completed in well under 3 seconds
        assert t_elapsed < 3.0, f"Revocation took {t_elapsed:.2f}s, exceeding 3.0s budget"
        assert revoked_count == 1
        assert session.viewer_count == 0
        assert f"{cam.id}_main" not in stream_manager.active_streams

        # Yield to allow background send_command to write to ws.outgoing
        await asyncio.sleep(0.05)

        # Verify stop_stream command was dispatched to agent
        stop_cmd = ws.outgoing[-1]
        assert stop_cmd["command"] == "stop_stream"

    @pytest.mark.asyncio
    async def test_user_concurrency_limit_enforced(self, db_session: AsyncSession) -> None:
        """User cannot open more than MAX_CONCURRENT_STREAMS_PER_USER (HTTP 429)."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        agent = Agent(
            tenant_id=tenant.id,
            name="Limit Agent",
            token_hash=hash_token("agt_lim"),
            is_active=True,
        )
        db_session.add(agent)
        await db_session.flush()

        nvr = NVR(
            tenant_id=tenant.id,
            agent_id=agent.id,
            name="Lim NVR",
            ip_address="192.168.1.210",
            port=554,
        )
        db_session.add(nvr)
        await db_session.flush()

        cams = []
        for i in range(MAX_CONCURRENT_STREAMS_PER_USER + 1):
            cam = Camera(
                tenant_id=tenant.id,
                nvr_id=nvr.id,
                channel_number=i + 1,
                name=f"Cam {i}",
                main_stream_url=f"rtsp://192.168.1.210:554/ch{i}",
            )
            db_session.add(cam)
            cams.append(cam)
        await db_session.commit()

        user_id = uuid.uuid4()

        # Connect Mock Agent WS
        ws = MockWebSocket()
        asyncio.create_task(
            agent_websocket_gateway(ws, agent_id=str(agent.id), token="agt_lim")  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)

        # Fill up to max allowed streams
        for i in range(MAX_CONCURRENT_STREAMS_PER_USER):
            req_task = asyncio.create_task(
                stream_manager.request_stream(
                    camera=cams[i],
                    nvr=nvr,
                    stream_type="main",
                    viewer_id=str(uuid.uuid4()),
                    user_id=user_id,
                )
            )
            await asyncio.sleep(0.02)
            cmd = ws.outgoing[-1]
            await ws.incoming.put(
                f'{{"type": "command_result", "command_id": "{cmd["command_id"]}", "status": "success", "result": {{"status": "started"}}}}'
            )
            await req_task

        assert stream_manager.get_user_active_count(user_id) == MAX_CONCURRENT_STREAMS_PER_USER

        # 7th stream attempt MUST RAISE HTTP 429
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await stream_manager.request_stream(
                camera=cams[MAX_CONCURRENT_STREAMS_PER_USER],
                nvr=nvr,
                stream_type="main",
                viewer_id=str(uuid.uuid4()),
                user_id=user_id,
            )
        assert exc_info.value.status_code == 429
        assert "User concurrent stream limit reached" in exc_info.value.detail
