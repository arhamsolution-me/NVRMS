"""Agent WebSocket Gateway: connection management, command dispatch, and heartbeat tracking."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, WebSocket, status

from hub_backend.logging_config import get_logger

log = get_logger(__name__)

COMMAND_WHITELIST: frozenset[str] = frozenset(
    [
        "ping",
        "get_status",
        "probe_nvr",
        "start_stream",
        "stop_stream",
        "reconcile_state",
    ]
)


class AgentConnection:
    """Represents an active WebSocket session with an edge agent."""

    def __init__(self, agent_id: str, websocket: WebSocket) -> None:
        self.agent_id = agent_id
        self.websocket = websocket
        self.connected_at = datetime.now(UTC)
        self.last_heartbeat_at = datetime.now(UTC)
        self.pending_responses: dict[str, asyncio.Future[dict[str, Any]]] = {}

    async def send_json(self, data: dict[str, Any]) -> None:
        await self.websocket.send_text(json.dumps(data))


class AgentManager:
    """Manages connected agents, duplicate connection arbitration, command dispatch, and revocation."""

    def __init__(self) -> None:
        self.active_agents: dict[str, AgentConnection] = {}
        self._lock = asyncio.Lock()

    async def register(self, agent_id: str, websocket: WebSocket) -> AgentConnection:
        """Register a new connection. Disconnects any existing connection for this agent ID."""
        async with self._lock:
            if agent_id in self.active_agents:
                old_conn = self.active_agents[agent_id]
                log.warning("duplicate_agent_connection_detected", agent_id=agent_id)
                with contextlib.suppress(Exception):
                    await old_conn.websocket.close(
                        code=4002, reason="Duplicate connection replaced"
                    )
                del self.active_agents[agent_id]

            conn = AgentConnection(agent_id=agent_id, websocket=websocket)
            self.active_agents[agent_id] = conn
            log.info("agent_connected", agent_id=agent_id)
            return conn

    async def unregister(self, agent_id: str) -> None:
        """Unregister an agent connection."""
        async with self._lock:
            if agent_id in self.active_agents:
                del self.active_agents[agent_id]
                log.info("agent_disconnected", agent_id=agent_id)

    async def revoke_agent(self, agent_id: str) -> None:
        """Immediately terminate any active connection for a revoked agent."""
        async with self._lock:
            if agent_id in self.active_agents:
                conn = self.active_agents[agent_id]
                with contextlib.suppress(Exception):
                    await conn.websocket.close(code=4003, reason="Agent revoked")
                del self.active_agents[agent_id]
                log.info("agent_connection_terminated_revoked", agent_id=agent_id)

    def is_online(self, agent_id: str) -> bool:
        """Check if an agent is currently connected."""
        return agent_id in self.active_agents

    def handle_response(self, agent_id: str, data: dict[str, Any]) -> None:
        """Route incoming command result/ack to its awaiting future."""
        conn = self.active_agents.get(agent_id)
        if not conn:
            return

        command_id = data.get("command_id")
        if command_id and command_id in conn.pending_responses:
            future = conn.pending_responses.pop(command_id)
            if not future.done():
                future.set_result(data)

    async def send_command(
        self,
        agent_id: str,
        command: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        """Dispatch a whitelisted command to an edge agent and await result."""
        if command not in COMMAND_WHITELIST:
            raise ValueError(f"Command '{command}' is not in the allowed command whitelist")

        conn = self.active_agents.get(agent_id)
        if not conn:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Agent '{agent_id}' is offline",
            )

        command_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        conn.pending_responses[command_id] = future

        envelope = {
            "type": "command",
            "command_id": command_id,
            "command": command,
            "payload": payload or {},
            "idempotency_key": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "timeout_seconds": timeout_seconds,
        }

        try:
            await conn.send_json(envelope)
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as exc:
            conn.pending_responses.pop(command_id, None)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Agent command '{command}' timed out after {timeout_seconds}s",
            ) from exc


agent_manager = AgentManager()
