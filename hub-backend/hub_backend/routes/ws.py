"""WebSocket endpoints for real-time client notifications."""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from hub_backend.security.tokens import decode_access_token
from hub_backend.ws.events import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/client")
async def websocket_client_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """Real-time event notification stream for authenticated frontend clients."""
    # Authenticate token
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = payload.sub
    role_id = payload.role_id

    await ws_manager.connect(websocket, user_id=user_id, role_id=role_id)
    try:
        while True:
            # Client ping/heartbeat loop
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id=user_id, role_id=role_id)
    except Exception:
        ws_manager.disconnect(websocket, user_id=user_id, role_id=role_id)
