"""WebSocket connection manager and real-time event broadcasting."""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import WebSocket

from hub_backend.logging_config import get_logger

log = get_logger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections grouped by user_id and tenant_id."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.user_connections: dict[str, list[WebSocket]] = {}
        self.role_connections: dict[str, list[WebSocket]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        role_id: str,
    ) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_connections.setdefault(user_id, []).append(websocket)
        self.role_connections.setdefault(role_id, []).append(websocket)
        log.info("ws_connected", user_id=user_id, role_id=role_id)

    def disconnect(
        self,
        websocket: WebSocket,
        user_id: str,
        role_id: str,
    ) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if user_id in self.user_connections:
            self.user_connections[user_id] = [
                ws for ws in self.user_connections[user_id] if ws != websocket
            ]
        if role_id in self.role_connections:
            self.role_connections[role_id] = [
                ws for ws in self.role_connections[role_id] if ws != websocket
            ]
        log.info("ws_disconnected", user_id=user_id, role_id=role_id)

    async def broadcast_to_role(self, role_id: str, event: str, data: dict[str, Any]) -> None:
        """Broadcast message to all connected clients having a specific role."""
        payload = json.dumps({"event": event, "data": data})
        connections = self.role_connections.get(role_id, [])
        for connection in list(connections):
            with contextlib.suppress(Exception):
                await connection.send_text(payload)

    async def broadcast_all(self, event: str, data: dict[str, Any]) -> None:
        """Broadcast message to all connected clients."""
        payload = json.dumps({"event": event, "data": data})
        for connection in list(self.active_connections):
            with contextlib.suppress(Exception):
                await connection.send_text(payload)


ws_manager = ConnectionManager()
