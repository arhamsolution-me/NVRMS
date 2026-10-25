"""Stage 2 tests: Agent Enrolment, Control Channel, Command Dispatch, and Revocation."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.agent import Agent, AgentEnrolmentToken
from hub_backend.models.tenant import Tenant
from hub_backend.security.tokens import hash_token


class TestAgentEnrolment:
    """Tests for single-use enrolment tokens and agent credential provisioning."""

    @pytest.mark.asyncio
    async def test_enrolment_code_generation_and_consumption(self, client: AsyncClient) -> None:
        """Admin generates code, agent consumes it, code becomes single-use."""
        # 1. Admin login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 2. Generate enrolment code
        gen_res = await client.post(
            "/api/v1/agents/enrol-token",
            headers=headers,
            json={"name": "Building 1 Agent"},
        )
        assert gen_res.status_code == 201
        token_data = gen_res.json()
        enrol_code = token_data["code"]
        assert enrol_code.startswith("ENROL-")

        # 3. Agent enrols with code
        enrol_res = await client.post(
            "/api/v1/agents/enrol",
            json={
                "enrolment_code": enrol_code,
                "name": "Building 1 Agent Production",
                "version": "1.0.0",
            },
        )
        assert enrol_res.status_code == 200
        cred = enrol_res.json()
        assert "agent_id" in cred
        assert cred["agent_token"].startswith("agt_")
        assert cred["name"] == "Building 1 Agent Production"

        # 4. Attempting to REUSE the code must be rejected with 400
        reuse_res = await client.post(
            "/api/v1/agents/enrol",
            json={"enrolment_code": enrol_code},
        )
        assert reuse_res.status_code == 400
        assert "already been used" in reuse_res.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_expired_enrolment_code_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Enrolment code past its 15-minute expiry must be rejected with 400."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        raw_code = f"ENROL-EXPIRED-{uuid.uuid4().hex[:4].upper()}"

        # Insert expired token
        past_time = datetime.now(UTC) - timedelta(minutes=16)
        token = AgentEnrolmentToken(
            tenant_id=tenant.id,
            code_hash=hash_token(raw_code),
            name="Expired Agent",
            created_by_user_id=(
                await db_session.execute(select(AgentEnrolmentToken.created_by_user_id).limit(1))
            ).scalar()
            or tenant.id,
            is_used=False,
            expires_at=past_time,
        )
        db_session.add(token)
        await db_session.commit()

        # Enrol attempt
        res = await client.post(
            "/api/v1/agents/enrol",
            json={"enrolment_code": raw_code},
        )
        assert res.status_code == 400
        assert "expired" in res.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_enrolment_code_rejected(self, client: AsyncClient) -> None:
        """Arbitrary non-existent enrolment code is rejected."""
        res = await client.post(
            "/api/v1/agents/enrol",
            json={"enrolment_code": "ENROL-NON-EXISTENT"},
        )
        assert res.status_code == 400
        assert "invalid" in res.json()["detail"].lower()


class TestAgentControlChannel:
    """Tests for agent connection gateway, duplicate handling, commands, and revocation."""

    @pytest.mark.asyncio
    async def test_agent_command_dispatch_and_whitelist(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Dispatching whitelisted command to online agent receives result; non-whitelisted rejected."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Create agent in DB
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        agent = Agent(
            tenant_id=tenant.id,
            name="Mock Agent",
            token_hash=hash_token("secret_agt_token"),
            is_active=True,
            status="online",
        )
        db_session.add(agent)
        await db_session.commit()

        # Non-whitelisted command must be rejected with 400
        bad_cmd_res = await client.post(
            f"/api/v1/agents/{agent.id}/command",
            headers=headers,
            json={"command": "reboot_machine_dangerously"},
        )
        assert bad_cmd_res.status_code == 400
        assert "whitelist" in bad_cmd_res.json()["detail"].lower()

        # Whitelisted command to offline agent returns 503
        offline_res = await client.post(
            f"/api/v1/agents/{agent.id}/command",
            headers=headers,
            json={"command": "ping"},
        )
        assert offline_res.status_code == 503
        assert "offline" in offline_res.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_agent_revocation_and_credential_rotation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Revoking agent marks status revoked; rotating credentials updates token."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        agent = Agent(
            tenant_id=tenant.id,
            name="Revoke Test Agent",
            token_hash=hash_token("init_token"),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.commit()

        # Rotate credentials
        rotate_res = await client.post(
            f"/api/v1/agents/{agent.id}/rotate-credentials",
            headers=headers,
        )
        assert rotate_res.status_code == 200
        new_token = rotate_res.json()["new_token"]
        assert new_token.startswith("agt_")

        # Revoke agent
        revoke_res = await client.post(
            f"/api/v1/agents/{agent.id}/revoke",
            headers=headers,
        )
        assert revoke_res.status_code == 200

        # Check agent detail reflects revoked status
        detail_res = await client.get(f"/api/v1/agents/{agent.id}", headers=headers)
        assert detail_res.status_code == 200
        assert detail_res.json()["is_active"] is False
        assert detail_res.json()["status"] == "revoked"


class MockWebSocket:
    """Mock WebSocket for end-to-end gateway protocol testing."""

    def __init__(self, headers: dict[str, str] | None = None, host: str = "127.0.0.1") -> None:
        self.headers = headers or {}
        self.client = type("Client", (), {"host": host})()
        self.incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self.outgoing: list[dict[str, Any]] = []
        self.is_closed = False
        self.close_code: int | None = None
        self.close_reason: str | None = None
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.is_closed = True
        self.close_code = code
        self.close_reason = reason

    async def receive_text(self) -> str:
        if self.is_closed:
            from fastapi import WebSocketDisconnect

            raise WebSocketDisconnect(code=self.close_code or 1000)
        msg = await self.incoming.get()
        if msg is None:
            from fastapi import WebSocketDisconnect

            raise WebSocketDisconnect(code=self.close_code or 1000)
        return msg

    async def send_text(self, text: str) -> None:
        import json

        self.outgoing.append(json.loads(text))


class TestAgentWSGatewayAndCRUD:
    """Tests for agent REST endpoints and WebSocket gateway protocol."""

    @pytest.mark.asyncio
    async def test_agent_list_and_detail(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Admin can list agents and fetch details."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # List agents
        list_res = await client.get("/api/v1/agents", headers=headers)
        assert list_res.status_code == 200
        assert isinstance(list_res.json(), list)

        # 404 for unknown agent
        fake_id = uuid.uuid4()
        not_found = await client.get(f"/api/v1/agents/{fake_id}", headers=headers)
        assert not_found.status_code == 404

    @pytest.mark.asyncio
    async def test_ws_auth_rejections(self, db_session: AsyncSession) -> None:
        """Invalid credentials, missing params, and revoked agents are rejected."""
        from hub_backend.routes.agent_ws import agent_websocket_gateway

        # 1. Missing credentials
        ws1 = MockWebSocket()
        await agent_websocket_gateway(ws1, agent_id="", token="")  # type: ignore[arg-type]
        assert ws1.is_closed
        assert ws1.close_code == 4001

        # 2. Invalid UUID format
        ws2 = MockWebSocket()
        await agent_websocket_gateway(ws2, agent_id="not-a-uuid", token="agt_tok")  # type: ignore[arg-type]
        assert ws2.is_closed
        assert ws2.close_code == 4001

        # 3. Non-existent agent
        ws3 = MockWebSocket()
        await agent_websocket_gateway(ws3, agent_id=str(uuid.uuid4()), token="agt_tok")  # type: ignore[arg-type]
        assert ws3.is_closed
        assert ws3.close_code == 4001

        # 4. Inactive/revoked agent
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        raw_tok = "secret_agent_token_revoked"
        revoked_agent = Agent(
            tenant_id=tenant.id,
            name="Revoked Agent For WS Test",
            token_hash=hash_token(raw_tok),
            is_active=False,
            status="revoked",
        )
        db_session.add(revoked_agent)
        await db_session.commit()

        ws4 = MockWebSocket()
        await agent_websocket_gateway(ws4, agent_id=str(revoked_agent.id), token=raw_tok)  # type: ignore[arg-type]
        assert ws4.is_closed
        assert ws4.close_code == 4003

    @pytest.mark.asyncio
    async def test_ws_gateway_lifecycle_heartbeat_and_reconciliation(
        self, db_session: AsyncSession
    ) -> None:
        """Agent connects, sends heartbeat and reconciliation, then disconnects."""
        import json

        from hub_backend.routes.agent_ws import agent_websocket_gateway
        from hub_backend.services.agent_manager import agent_manager

        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        raw_tok = "agt_valid_token_for_lifecycle"
        agent = Agent(
            tenant_id=tenant.id,
            name="Lifecycle Agent",
            token_hash=hash_token(raw_tok),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.commit()

        ws = MockWebSocket()
        task = asyncio.create_task(
            agent_websocket_gateway(ws, agent_id=str(agent.id), token=raw_tok)  # type: ignore[arg-type]
        )
        # Give gateway time to accept
        await asyncio.sleep(0.05)
        assert ws.accepted
        assert agent_manager.is_online(str(agent.id))

        # Send heartbeat
        await ws.incoming.put(
            json.dumps(
                {"type": "heartbeat", "version": "1.2.3", "timestamp": "2026-10-25T12:00:00Z"}
            )
        )
        await asyncio.sleep(0.05)

        # Check heartbeat ack received
        assert len(ws.outgoing) >= 1
        ack = ws.outgoing[0]
        assert ack["type"] == "heartbeat_ack"

        # Send reconciliation
        await ws.incoming.put(
            json.dumps({"type": "reconciliation", "payload": {"active_streams": ["s1"]}})
        )
        await asyncio.sleep(0.05)

        # Disconnect agent
        await ws.incoming.put(None)
        await task
        assert not agent_manager.is_online(str(agent.id))

    @pytest.mark.asyncio
    async def test_ws_duplicate_connection_drops_previous(self, db_session: AsyncSession) -> None:
        """Duplicate connection with same agent ID cleanly closes previous socket with code 4002."""
        from hub_backend.routes.agent_ws import agent_websocket_gateway
        from hub_backend.services.agent_manager import agent_manager

        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        raw_tok = "agt_duplicate_test_token"
        agent = Agent(
            tenant_id=tenant.id,
            name="Duplicate Test Agent",
            token_hash=hash_token(raw_tok),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.commit()

        # Connect ws1
        ws1 = MockWebSocket()
        task1 = asyncio.create_task(
            agent_websocket_gateway(ws1, agent_id=str(agent.id), token=raw_tok)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        assert ws1.accepted
        assert agent_manager.is_online(str(agent.id))

        # Connect ws2 with same agent_id
        ws2 = MockWebSocket()
        task2 = asyncio.create_task(
            agent_websocket_gateway(ws2, agent_id=str(agent.id), token=raw_tok)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        assert ws2.accepted

        # ws1 must be closed with 4002
        assert ws1.is_closed
        assert ws1.close_code == 4002

        # Clean disconnect ws2
        await ws2.incoming.put(None)
        await task2
        task1.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task1

    @pytest.mark.asyncio
    async def test_ws_roundtrip_command_execution(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Admin dispatches command, connected agent receives it and replies, admin gets result."""
        import json

        from hub_backend.routes.agent_ws import agent_websocket_gateway

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        raw_tok = "agt_roundtrip_cmd_token"
        agent = Agent(
            tenant_id=tenant.id,
            name="Command Agent",
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

        # Start command dispatch in background
        cmd_task = asyncio.create_task(
            client.post(
                f"/api/v1/agents/{agent.id}/command",
                headers=headers,
                json={"command": "ping", "payload": {"foo": "bar"}},
            )
        )
        await asyncio.sleep(0.05)

        # Verify ws received command envelope
        assert len(ws.outgoing) >= 1
        cmd_envelope = ws.outgoing[-1]
        assert cmd_envelope["command"] == "ping"
        cmd_id = cmd_envelope["command_id"]

        # Reply from agent
        reply_msg = json.dumps(
            {
                "type": "command_result",
                "command_id": cmd_id,
                "status": "success",
                "result": {"status": "pong", "echo": "bar"},
            }
        )
        await ws.incoming.put(reply_msg)

        # Admin HTTP request resolves successfully!
        res = await cmd_task
        assert res.status_code == 200
        cmd_body = res.json()
        assert cmd_body["status"] == "success"
        assert cmd_body["result"]["status"] == "pong"

        # Disconnect
        await ws.incoming.put(None)
        await gw_task
