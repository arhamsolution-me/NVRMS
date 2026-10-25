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
        "check_disk",
        "sync_time",
        "apply_update",
        "check_network",
        "get_diagnostics",
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
        from agent.resilience.time_sync import time_sync_manager
        from agent.streaming.manager import agent_stream_manager

        return {
            "active_streams": agent_stream_manager.list_active_streams(),
            "devices": [],
            "timestamp": time_sync_manager.get_compensated_iso(),
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

    if command == "check_disk":
        from agent.resilience.disk_monitor import disk_monitor

        target_path = payload.get("path", ".")
        prune = payload.get("prune", False)
        stats = disk_monitor.get_disk_stats(target_path)
        pruned = []
        if prune:
            pruned = disk_monitor.prune_old_logs(target_path, force=True)
        return {"stats": stats, "pruned": pruned}

    if command == "sync_time":
        from agent.resilience.time_sync import time_sync_manager

        server_ts = payload.get("server_timestamp", datetime.now(UTC).isoformat())
        skew = time_sync_manager.sync_with_server(server_ts)
        return {
            "skew_seconds": skew,
            "is_skewed": time_sync_manager.is_skewed,
            "compensated_iso": time_sync_manager.get_compensated_iso(),
        }

    if command == "apply_update":
        from agent.resilience.updater import agent_updater

        return agent_updater.apply_update(
            current_file=payload.get("current_file", ""),
            new_package=payload.get("new_package", ""),
            expected_sha256=payload.get("expected_sha256", ""),
            signature=payload.get("signature", ""),
        )

    if command == "check_network":
        from agent.resilience.network_monitor import network_monitor

        packet_loss = float(payload.get("packet_loss_pct", 0.0))
        rtt = float(payload.get("rtt_ms", 20.0))
        return network_monitor.evaluate_metrics(packet_loss_pct=packet_loss, rtt_ms=rtt)

    if command == "get_diagnostics":
        from agent.diagnostics import diagnostics_collector

        return diagnostics_collector.collect_bundle()

    raise ValueError(f"Unhandled command: {command}")
