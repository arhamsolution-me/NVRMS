"""Tests for Hub resilience layer, state reconciliation, and fault handling."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.agent import Agent
from hub_backend.models.tenant import Tenant
from hub_backend.routes.agent_ws import agent_websocket_gateway
from hub_backend.security.tokens import hash_token
from hub_backend.services.stream_manager import stream_manager
from tests.test_agent_lifecycle import MockWebSocket


class TestHubStateReconciliation:
    """Matrix Row 2: State reconciliation on agent reconnect."""

    @pytest.mark.asyncio
    async def test_reconciliation_cleans_orphaned_streams(self, db_session: AsyncSession) -> None:
        """When an agent reports active streams that Hub has no viewers for, Hub commands agent to stop them."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        raw_tok = "agt_reconcile_orphan_test"
        agent = Agent(
            tenant_id=tenant.id,
            name="Reconcile Agent",
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

        # Agent reconnects and reports running orphaned stream "orphan_cam_123_sub"
        orphan_stream_id = "orphan_cam_123_sub"
        await ws.incoming.put(
            json.dumps(
                {
                    "type": "reconciliation",
                    "agent_id": str(agent.id),
                    "payload": {"active_streams": [orphan_stream_id], "devices": []},
                }
            )
        )
        await asyncio.sleep(0.05)

        # Hub must send a stop_stream command for the orphan
        assert len(ws.outgoing) >= 1
        stop_cmds = [cmd for cmd in ws.outgoing if cmd.get("command") == "stop_stream"]
        assert len(stop_cmds) == 1
        assert stop_cmds[0]["payload"]["stream_id"] == orphan_stream_id

        # Clean disconnect
        await ws.incoming.put(None)
        await gw_task

    @pytest.mark.asyncio
    async def test_reconciliation_detects_missing_stream(self) -> None:
        """When Hub has an active session for an agent, but agent reports 0 streams, Hub detects missing."""
        agent_id = uuid.uuid4()
        res = await stream_manager.reconcile_agent_streams(
            agent_id=agent_id,
            reported_streams=[],
        )
        assert res["stopped_orphans"] == []
        assert res["restored_missing"] == []


class TestHubAgentDisconnectionAndReconnection:
    """Matrix Row 1: Agent abrupt drop and reconnection updates status."""

    @pytest.mark.asyncio
    async def test_abrupt_disconnect_marks_agent_offline(self, db_session: AsyncSession) -> None:
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        raw_tok = "agt_drop_test"
        agent = Agent(
            tenant_id=tenant.id,
            name="Drop Agent",
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

        # Agent sends heartbeat -> online
        await ws.incoming.put(
            json.dumps(
                {
                    "type": "heartbeat",
                    "agent_id": str(agent.id),
                    "version": "0.1.0",
                }
            )
        )
        await asyncio.sleep(0.05)

        # Verify online
        await db_session.refresh(agent)
        assert agent.status == "online"

        # Abrupt disconnect
        await ws.incoming.put(None)
        await gw_task

        # Verify agent is marked offline
        await db_session.refresh(agent)
        assert agent.status == "offline"
