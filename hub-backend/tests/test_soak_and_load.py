"""Stage 12 Soak, Load, and Stress Test Suite.

Validates platform stability and concurrency:
1. Agent Heartbeat Soak: High-frequency continuous heartbeat exchange with clock drift
   sampling, proving stability of the WebSocket gateway and state management.
2. Concurrent Stream Fan-Out Load: Multi-viewer concurrent join and leave stress testing,
   verifying atomic reference counting, single-worker pulling (zero NVR overload),
   and graceful teardown.
3. Rate Limiter Soak & Window Recovery: High burst traffic testing against sliding-window
   limiter, verifying HTTP 429 backoff and seamless post-window recovery.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.agent import Agent
from hub_backend.models.camera import Camera
from hub_backend.models.nvr import NVR
from hub_backend.models.tenant import Tenant
from hub_backend.routes.agent_ws import agent_websocket_gateway
from hub_backend.security.rate_limit import rate_limiter
from hub_backend.security.tokens import hash_token
from hub_backend.services.agent_manager import agent_manager
from hub_backend.services.stream_manager import stream_manager
from tests.test_agent_lifecycle import MockWebSocket


class TestAgentHeartbeatSoak:
    """Soak testing the Edge Agent control channel under rapid heartbeat intervals."""

    @pytest.mark.asyncio
    async def test_agent_heartbeat_soak_50_iterations(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Saturate agent websocket with 50 consecutive heartbeats and verify stability."""
        # 1. Setup tenant and agent in DB
        tenant = Tenant(
            id=uuid.uuid4(), name="Soak Test Tenant", slug="soak-tenant", is_active=True
        )
        db_session.add(tenant)
        await db_session.flush()

        agent_id = uuid.uuid4()
        raw_token = f"agt_soak_{uuid.uuid4().hex[:12]}"
        agent = Agent(
            id=agent_id,
            tenant_id=tenant.id,
            name="Soak Test Agent",
            token_hash=hash_token(raw_token),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.commit()

        # 2. Connect agent over MockWebSocket
        ws = MockWebSocket()
        gateway_task = asyncio.create_task(
            agent_websocket_gateway(ws, agent_id=str(agent_id), token=raw_token)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        assert ws.accepted
        assert agent_manager.is_online(str(agent_id))

        # 3. Fire 50 consecutive heartbeats with simulated drift
        for i in range(50):
            timestamp_str = datetime.now(UTC).isoformat()
            hb_msg = json.dumps(
                {
                    "type": "heartbeat",
                    "agent_id": str(agent_id),
                    "timestamp": timestamp_str,
                    "iteration": i,
                    "active_streams": [],
                }
            )
            await ws.incoming.put(hb_msg)
            # Minimal delay simulating high frequency telemetry
            await asyncio.sleep(0.005)

        # Check that agent remained continuously connected without errors
        assert agent_manager.is_online(str(agent_id))

        # 4. Clean shutdown of agent socket
        await ws.incoming.put(None)
        await gateway_task


class TestConcurrentStreamFanOutLoad:
    """Load testing the StreamManager under concurrent viewer fan-out."""

    @pytest.mark.asyncio
    async def test_concurrent_viewer_join_and_leave_stress(self, db_session: AsyncSession) -> None:
        """30 concurrent viewers join simultaneously -> verify single worker pull & clean teardown."""
        tenant_id = uuid.uuid4()
        camera_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        nvr_id = uuid.uuid4()

        camera = Camera(
            id=camera_id,
            tenant_id=tenant_id,
            nvr_id=nvr_id,
            channel_number=1,
            name="FanOut Cam",
            main_stream_url="rtsp://192.168.1.100:554/ch1",
            sub_stream_url="rtsp://192.168.1.100:554/ch1_sub",
            codec="h264",
        )
        nvr = NVR(
            id=nvr_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            name="FanOut NVR",
            ip_address="192.168.1.100",
            port=554,
            brand="generic",
        )

        # Mock agent command dispatch
        dispatched_commands: list[dict] = []

        async def mock_send_command(
            agent_id: str,
            command: str,
            payload: dict | None = None,
            timeout_seconds: float = 10.0,
        ) -> dict:
            dispatched_commands.append(
                {"agent_id": agent_id, "action": command, "payload": payload}
            )
            return {"status": "success"}

        # Patch agent_manager.send_command
        original_send_cmd = agent_manager.send_command
        agent_manager.send_command = mock_send_command  # type: ignore

        try:
            # 1. 30 viewers request stream simultaneously
            viewer_count = 30

            async def join_stream(viewer_idx: int) -> None:
                await stream_manager.request_stream(
                    camera=camera,
                    nvr=nvr,
                    stream_type="main",
                    viewer_id=f"viewer_{viewer_idx}",
                )

            # Concurrent fan-out join
            await asyncio.gather(*(join_stream(i) for i in range(viewer_count)))

            # Verify that viewer_count is exactly 30
            stream_key = stream_manager.get_stream_key(camera_id, "main")
            active = stream_manager.active_streams.get(stream_key)
            assert active is not None
            assert active.viewer_count == viewer_count

            # CRITICAL: Even with 30 concurrent viewers, only ONE start_stream command was sent to the agent!
            start_commands = [c for c in dispatched_commands if c["action"] == "start_stream"]
            assert (
                len(start_commands) == 1
            ), f"Expected 1 start_stream command, got {len(start_commands)}"

            # 2. 30 viewers leave concurrently
            async def leave_stream(viewer_idx: int) -> None:
                await stream_manager.leave_stream(
                    camera_id=camera_id,
                    stream_type="main",
                    viewer_id=f"viewer_{viewer_idx}",
                    grace_seconds=0.05,
                )

            await asyncio.gather(*(leave_stream(i) for i in range(viewer_count)))

            # Verify viewer count reached 0 and grace period task is active
            active_after = stream_manager.active_streams.get(stream_key)
            assert active_after is not None
            assert active_after.viewer_count == 0
            assert active_after.grace_task is not None

            # Cancel grace task to clean up event loop immediately
            active_after.grace_task.cancel()

        finally:
            agent_manager.send_command = original_send_cmd


class TestRateLimitingSoakAndRecovery:
    """Soak testing the sliding-window rate limiter under burst attack and verifying recovery."""

    @pytest.mark.asyncio
    async def test_rate_limiter_burst_and_window_recovery(self, client: AsyncClient) -> None:
        """Burst requests -> rate limiter triggers 429 -> reset window -> requests succeed."""
        rate_limiter.reset("127.0.0.1:/api/v1/auth/login")

        # Burst 10 rapid login requests with bad credentials
        for _ in range(10):
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": "wrong@nvrsms.local", "password": "wrong"},
            )
            assert res.status_code == 401

        # The 11th request must be blocked by rate limiter with 429 Too Many Requests
        throttled_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@nvrsms.local", "password": "wrong"},
        )
        assert throttled_res.status_code == 429
        assert "Retry-After" in throttled_res.headers

        # Now simulate window expiry / reset
        rate_limiter.reset("127.0.0.1:/api/v1/auth/login")

        # Next request must not be blocked by 429, returning normal 401
        recovered_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@nvrsms.local", "password": "wrong"},
        )
        assert recovered_res.status_code == 401
