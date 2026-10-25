"""Stage 4 Hub tests: Stream tokens, MediaMTX auth webhook, on-demand streaming, and 1:N fan-out."""

from __future__ import annotations

import asyncio
import json
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
    verify_stream_token,
)
from hub_backend.security.tokens import hash_token
from hub_backend.services.stream_manager import stream_manager
from tests.test_agent_lifecycle import MockWebSocket


class TestStreamTokens:
    """Tests for short-lived user-bound cryptographic stream tokens."""

    def test_create_and_verify_stream_token_success(self) -> None:
        """Valid stream token decodes with all required claims."""
        uid = uuid.uuid4()
        cid = uuid.uuid4()
        tid = uuid.uuid4()

        token = create_stream_token(
            user_id=uid,
            camera_id=cid,
            tenant_id=tid,
            stream_type="main",
            expires_in_seconds=60,
        )
        assert isinstance(token, str)

        payload = verify_stream_token(token)
        assert payload["sub"] == str(uid)
        assert payload["camera_id"] == str(cid)
        assert payload["tenant_id"] == str(tid)
        assert payload["stream_type"] == "main"
        assert payload["token_type"] == "stream_playback"

    def test_expired_token_rejected(self) -> None:
        """Expired stream token raises ValueError."""
        token = create_stream_token(
            user_id=uuid.uuid4(),
            camera_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            expires_in_seconds=-5,  # already expired
        )
        with pytest.raises(ValueError, match="expired"):
            verify_stream_token(token)

    def test_tampered_token_rejected(self) -> None:
        """Corrupted signature raises ValueError."""
        token = create_stream_token(
            user_id=uuid.uuid4(),
            camera_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
        )
        corrupted = token[:-5] + "XXXXX"
        with pytest.raises(ValueError):
            verify_stream_token(corrupted)


class TestMediaMTXAuthWebhook:
    """Tests for external auth webhook invoked by MediaMTX."""

    @pytest.mark.asyncio
    async def test_publish_auth_with_valid_agent_token(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Agent publishing with valid agent token is accepted (HTTP 200)."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        raw_agent_tok = "agt_mediamtx_publish_test_tok"

        agent = Agent(
            tenant_id=tenant.id,
            name="Publishing Test Agent",
            token_hash=hash_token(raw_agent_tok),
            is_active=True,
            status="online",
        )
        db_session.add(agent)
        await db_session.commit()

        # MediaMTX publish request with agent token in password
        res = await client.post(
            "/api/v1/streams/auth",
            json={
                "action": "publish",
                "path": "live/test_stream_id",
                "password": raw_agent_tok,
            },
        )
        assert res.status_code == 200

        # Wrong token -> 403
        bad_res = await client.post(
            "/api/v1/streams/auth",
            json={
                "action": "publish",
                "path": "live/test_stream_id",
                "password": "wrong_agent_token",
            },
        )
        assert bad_res.status_code == 403

    @pytest.mark.asyncio
    async def test_read_auth_with_valid_and_mismatched_stream_token(
        self, client: AsyncClient
    ) -> None:
        """Reading with valid stream token matching path returns 200; mismatched path returns 403."""
        cid = uuid.uuid4()
        token = create_stream_token(
            user_id=uuid.uuid4(),
            camera_id=cid,
            tenant_id=uuid.uuid4(),
            stream_type="sub",
        )

        # Matching path
        matching_path = f"live/{cid}_sub"
        res_ok = await client.post(
            "/api/v1/streams/auth",
            json={
                "action": "read",
                "path": matching_path,
                "query": f"token={token}",
            },
        )
        assert res_ok.status_code == 200

        # Mismatched path (wrong camera id or stream type)
        wrong_path = f"live/{uuid.uuid4()}_sub"
        res_mismatch = await client.post(
            "/api/v1/streams/auth",
            json={
                "action": "read",
                "path": wrong_path,
                "query": f"token={token}",
            },
        )
        assert res_mismatch.status_code == 403


class TestOnDemandStreamingAndFanOut:
    """Tests for on-demand start_stream, 1:N viewer fan-out, and grace period stop."""

    @pytest.mark.asyncio
    async def test_fanout_and_grace_period(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """First viewer starts stream, second viewer shares stream (single pull), grace period stops stream."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        # Connect Agent
        raw_tok = "agt_streaming_pipeline_test"
        agent = Agent(
            tenant_id=tenant.id,
            name="Stream Agent",
            token_hash=hash_token(raw_tok),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.commit()

        ws = MockWebSocket()
        gw_task = asyncio.create_task(
            agent_websocket_gateway(ws, agent_id=str(agent.id), token=raw_tok)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        assert ws.accepted

        # Create NVR and Camera
        nvr = NVR(
            tenant_id=tenant.id,
            agent_id=agent.id,
            name="Streaming NVR",
            ip_address="192.168.1.150",
            port=554,
        )
        db_session.add(nvr)
        await db_session.flush()

        cam = Camera(
            tenant_id=tenant.id,
            nvr_id=nvr.id,
            channel_number=1,
            name="Fanout Cam",
            main_stream_url="rtsp://192.168.1.150:554/ch1/main",
            sub_stream_url="rtsp://192.168.1.150:554/ch1/sub",
        )
        db_session.add(cam)
        await db_session.commit()

        # ── 1. First viewer requests stream ─────────────────────────────
        req1_task = asyncio.create_task(
            client.post(
                f"/api/v1/streams/{cam.id}/token",
                headers=headers,
                json={"stream_type": "sub"},
            )
        )
        await asyncio.sleep(0.05)

        # Agent receives start_stream command
        assert len(ws.outgoing) >= 1
        start_cmd = ws.outgoing[-1]
        assert start_cmd["command"] == "start_stream"
        start_cmd_id = start_cmd["command_id"]

        # Agent replies that stream started
        await ws.incoming.put(
            json.dumps(
                {
                    "type": "command_result",
                    "command_id": start_cmd_id,
                    "status": "success",
                    "result": {"status": "started", "stream_id": f"{cam.id}_sub"},
                }
            )
        )

        res1 = await req1_task
        assert res1.status_code == 200
        token_data1 = res1.json()
        viewer1_id = token_data1["viewer_id"]
        assert token_data1["stream_id"] == f"{cam.id}_sub"

        # Check active streams has 1 session with 1 viewer
        active_res1 = await client.get("/api/v1/streams/active", headers=headers)
        assert active_res1.status_code == 200
        active_list1 = active_res1.json()
        assert len(active_list1) == 1
        assert active_list1[0]["viewer_count"] == 1

        # ── 2. Second viewer requests same stream (Fan-Out) ──────────────
        outgoing_count_before = len(ws.outgoing)
        res2 = await client.post(
            f"/api/v1/streams/{cam.id}/token",
            headers=headers,
            json={"stream_type": "sub"},
        )
        assert res2.status_code == 200
        token_data2 = res2.json()
        viewer2_id = token_data2["viewer_id"]
        assert viewer2_id != viewer1_id

        # CRITICAL VERIFICATION: No second start_stream command was sent to agent!
        assert len(ws.outgoing) == outgoing_count_before

        # Check active streams now has 2 viewers
        active_res2 = await client.get("/api/v1/streams/active", headers=headers)
        active_list2 = active_res2.json()
        assert active_list2[0]["viewer_count"] == 2

        # ── 3. First viewer stops ────────────────────────────────────────
        stop_res1 = await client.post(
            f"/api/v1/streams/{cam.id}/stop",
            headers=headers,
            json={"viewer_id": viewer1_id, "stream_type": "sub"},
        )
        assert stop_res1.status_code == 200

        # Stream remains active with 1 viewer
        active_res3 = await client.get("/api/v1/streams/active", headers=headers)
        assert active_res3.json()[0]["viewer_count"] == 1

        # ── 4. Second viewer stops with short grace period ───────────────
        await stream_manager.leave_stream(
            camera_id=cam.id,
            stream_type="sub",
            viewer_id=viewer2_id,
            grace_seconds=0.1,  # Short grace period for test
        )

        # Allow grace period to fire
        await asyncio.sleep(0.2)

        # Verify agent received stop_stream command
        assert len(ws.outgoing) > outgoing_count_before
        stop_cmd = ws.outgoing[-1]
        assert stop_cmd["command"] == "stop_stream"

        # Agent replies that stream stopped
        await ws.incoming.put(
            json.dumps(
                {
                    "type": "command_result",
                    "command_id": stop_cmd["command_id"],
                    "status": "success",
                    "result": {"status": "stopped", "stream_id": f"{cam.id}_sub"},
                }
            )
        )
        await asyncio.sleep(0.05)

        # Active stream is now cleaned up
        active_res4 = await client.get("/api/v1/streams/active", headers=headers)
        assert len(active_res4.json()) == 0

        # Clean disconnect ws
        await ws.incoming.put(None)
        await gw_task
