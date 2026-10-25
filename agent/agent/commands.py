"""Agent command processor and whitelist validator."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from agent.logging_config import get_logger

log = get_logger(__name__)

START_TIME = time.time()

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


async def execute_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a local agent command from the whitelist."""
    if command not in COMMAND_WHITELIST:
        raise ValueError(f"Command '{command}' is not in the allowed command whitelist")

    if command == "ping":
        return {
            "status": "pong",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    if command == "get_status":
        uptime = int(time.time() - START_TIME)
        return {
            "status": "healthy",
            "uptime_seconds": uptime,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    if command == "reconcile_state":
        return {
            "active_streams": [],
            "devices": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    if command == "probe_nvr":
        from agent.discovery.nvr_probe import probe_nvr as run_probe

        target_ip = payload.get("ip", "")
        port = int(payload.get("port", 554))
        username = payload.get("username", "admin")
        password = payload.get("password", "")
        brand = payload.get("brand", "auto")

        return await run_probe(
            ip=target_ip,
            port=port,
            username=username,
            password=password,
            brand=brand,
        )

    if command == "start_stream":
        from agent.streaming.manager import agent_stream_manager

        return await agent_stream_manager.start_stream(
            stream_id=payload.get("stream_id", ""),
            source_url=payload.get("source_url", ""),
            target_path=payload.get("target_path", ""),
            codec=payload.get("codec", "h264"),
            transcode_h265=payload.get("transcode_h265", False),
        )

    if command == "stop_stream":
        from agent.streaming.manager import agent_stream_manager

        return await agent_stream_manager.stop_stream(
            stream_id=payload.get("stream_id", ""),
        )

    raise ValueError(f"Unhandled command: {command}")
