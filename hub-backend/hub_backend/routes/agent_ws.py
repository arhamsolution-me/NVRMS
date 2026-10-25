"""Agent WebSocket Gateway: bi-directional control channel."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from hub_backend.db import AsyncSessionLocal
from hub_backend.logging_config import get_logger
from hub_backend.models.agent import Agent
from hub_backend.security.tokens import hash_token
from hub_backend.services.agent_manager import agent_manager
from hub_backend.services.stream_manager import stream_manager

log = get_logger(__name__)
router = APIRouter(tags=["agent_ws"])


@router.websocket("/ws/agent")
async def agent_websocket_gateway(
    websocket: WebSocket,
    agent_id: str = Query(default=""),
    token: str = Query(default=""),
) -> None:
    """Outbound control channel established from edge agent to hub."""
    # Fallback to headers if not in query params
    if not agent_id:
        agent_id = websocket.headers.get("x-agent-id", "")
    if not token:
        auth_hdr = websocket.headers.get("authorization", "")
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()

    if not agent_id or not token:
        await websocket.close(code=4001, reason="Missing agent_id or token credentials")
        return

    # Verify agent credentials in database
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid agent_id UUID format")
        return

    hashed_token = hash_token(token)

    async with AsyncSessionLocal() as session:
        stmt = select(Agent).where(Agent.id == agent_uuid)
        res = await session.execute(stmt)
        agent = res.scalar_one_or_none()

        if not agent or agent.token_hash != hashed_token:
            await websocket.close(code=4001, reason="Invalid agent credentials")
            return

        if not agent.is_active:
            await websocket.close(code=4003, reason="Agent is revoked")
            return

        # Mark agent online
        agent.status = "online"
        agent.last_heartbeat_at = datetime.now(UTC)
        if websocket.client:
            agent.last_ip_address = websocket.client.host
        await session.commit()

    # Accept connection and register with agent_manager
    await websocket.accept()
    conn = await agent_manager.register(agent_id, websocket)

    log.info("agent_gateway_connected", agent_id=agent_id)

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                data: dict[str, Any] = json.loads(raw_msg)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "heartbeat":
                conn.last_heartbeat_at = datetime.now(UTC)
                async with AsyncSessionLocal() as session:
                    db_agent = await session.get(Agent, agent_uuid)
                    if db_agent:
                        db_agent.last_heartbeat_at = conn.last_heartbeat_at
                        db_agent.status = "online"
                        if "version" in data:
                            db_agent.version = data["version"]
                        await session.commit()

                await conn.send_json(
                    {
                        "type": "heartbeat_ack",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )

            elif msg_type == "command_result":
                agent_manager.handle_response(agent_id, data)

            elif msg_type == "reconciliation":
                # Agent state sync upon connect
                payload = data.get("payload", {})
                reported_streams = payload.get("active_streams", [])
                reconciled = await stream_manager.reconcile_agent_streams(
                    agent_uuid, reported_streams
                )
                log.info(
                    "agent_state_reconciled",
                    agent_id=agent_id,
                    reported_streams=len(reported_streams),
                    stopped_orphans=len(reconciled["stopped_orphans"]),
                    restored_missing=len(reconciled["restored_missing"]),
                )

    except WebSocketDisconnect:
        log.info("agent_gateway_disconnected", agent_id=agent_id)
    except Exception as exc:
        log.warning("agent_gateway_error", agent_id=agent_id, error=str(exc))
    finally:
        await agent_manager.unregister(agent_id)
        async with AsyncSessionLocal() as session:
            db_agent = await session.get(Agent, agent_uuid)
            if db_agent and db_agent.status != "revoked":
                db_agent.status = "offline"
                await session.commit()
