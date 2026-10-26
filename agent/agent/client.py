"""Agent WebSocket control client with exponential backoff, jitter, and heartbeat."""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from agent.commands import execute_command
from agent.config import get_settings
from agent.logging_config import get_logger

log = get_logger(__name__)


async def enrol_agent(
    hub_url: str,
    enrolment_code: str,
    name: str | None = None,
    version: str = "0.1.0",
    allow_insecure_transport: bool = True,
) -> dict[str, Any]:
    """Perform bootstrap enrolment call to the Hub to obtain permanent agent credentials."""
    if not allow_insecure_transport and hub_url.startswith("http://"):
        raise ValueError(
            "Plaintext transport refused: http:// is prohibited. Transport security requires https://."
        )
    enrol_url = f"{hub_url.rstrip('/')}/api/v1/agents/enrol"
    payload = {
        "enrolment_code": enrolment_code.strip(),
        "name": name,
        "version": version,
    }
    async with httpx.AsyncClient(timeout=10.0) as http:
        res = await http.post(enrol_url, json=payload)
        if res.status_code != 200:
            error_detail = res.text
            try:
                error_detail = res.json().get("detail", res.text)
            except Exception:
                pass
            raise RuntimeError(f"Agent enrolment failed (HTTP {res.status_code}): {error_detail}")
        return res.json()  # type: ignore[no-any-return]


class AgentClient:
    """Persistent edge agent control channel manager."""

    def __init__(
        self,
        agent_id: str,
        agent_token: str,
        hub_url: str,
        heartbeat_interval: float = 30.0,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        pinned_cert_fingerprint: str | None = None,
        backup_cert_fingerprint: str | None = None,
        allow_insecure_transport: bool = True,
    ) -> None:
        self.agent_id = agent_id
        self.agent_token = agent_token
        self.hub_url = hub_url
        self.heartbeat_interval = heartbeat_interval
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.pinned_cert_fingerprint = pinned_cert_fingerprint
        self.backup_cert_fingerprint = backup_cert_fingerprint
        self.allow_insecure_transport = allow_insecure_transport
        self._running = False
        self._connected = False
        self.ws: websockets.WebSocketClientProtocol | None = None  # type: ignore[name-defined]

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_ws_url(self) -> str:
        """Construct WebSocket connection URL."""
        if not self.allow_insecure_transport and self.hub_url.startswith("http://"):
            raise ValueError(
                "Plaintext transport refused: http:// is prohibited. Transport security requires https:// / wss://."
            )
        base = self.hub_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
        if not self.allow_insecure_transport and base.startswith("ws://"):
            raise ValueError(
                "Plaintext transport refused: ws:// is prohibited. Transport security requires wss://."
            )
        return f"{base}/ws/agent?agent_id={self.agent_id}&token={self.agent_token}"

    def compute_backoff(self, attempt: int) -> float:
        """Compute exponential backoff with +/- 25% jitter."""
        exp_delay = min(self.max_delay, self.base_delay * (2 ** min(attempt, 6)))
        jitter = secrets.SystemRandom().uniform(-0.25, 0.25) * exp_delay
        return max(self.base_delay, exp_delay + jitter)

    async def _heartbeat_loop(self, ws: websockets.WebSocketClientProtocol) -> None:  # type: ignore[name-defined]
        """Periodic heartbeat sender."""
        settings = get_settings()
        while self._running and self._connected:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                heartbeat_msg = {
                    "type": "heartbeat",
                    "agent_id": self.agent_id,
                    "version": settings.agent_version,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await ws.send(json.dumps(heartbeat_msg))
                log.debug("agent_heartbeat_sent", agent_id=self.agent_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("agent_heartbeat_failed", error=str(exc))
                break

    async def _handle_message(
        self,
        ws: websockets.WebSocketClientProtocol,
        raw_msg: str,  # type: ignore[name-defined]
    ) -> None:
        """Process incoming messages from the Hub."""
        try:
            msg: dict[str, Any] = json.loads(raw_msg)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")

        if msg_type == "command":
            command_id = msg.get("command_id", "")
            cmd_name = msg.get("command", "")
            payload = msg.get("payload", {})

            try:
                result = await execute_command(cmd_name, payload)
                response = {
                    "type": "command_result",
                    "command_id": command_id,
                    "status": "success",
                    "result": result,
                }
            except Exception as exc:
                log.warning("agent_command_execution_error", command=cmd_name, error=str(exc))
                response = {
                    "type": "command_result",
                    "command_id": command_id,
                    "status": "error",
                    "error": str(exc),
                }

            await ws.send(json.dumps(response))

        elif msg_type == "heartbeat_ack":
            ts = msg.get("timestamp")
            if ts:
                from agent.resilience.time_sync import time_sync_manager

                time_sync_manager.sync_with_server(ts)
            log.debug("agent_heartbeat_ack_received", timestamp=ts)

    async def connect_once(self) -> None:
        """Establish one connection session and process messages until closed."""
        ws_url = self.get_ws_url()
        log.info("agent_connecting", url=ws_url.split("?")[0])

        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            self.ws = ws
            self._connected = True
            log.info("agent_control_channel_established", agent_id=self.agent_id)

            if (
                (self.pinned_cert_fingerprint or self.backup_cert_fingerprint)
                and hasattr(ws, "transport")
                and ws.transport
            ):
                ssl_obj = ws.transport.get_extra_info("ssl_object")
                if ssl_obj:
                    der_cert = ssl_obj.getpeercert(binary_form=True)
                    if der_cert:
                        from agent.security.pinning import CertificatePinningVerifier

                        CertificatePinningVerifier(
                            pinned_fingerprint_sha256=self.pinned_cert_fingerprint,
                            backup_fingerprint_sha256=self.backup_cert_fingerprint,
                        ).verify_cert_der(der_cert)

            from agent.resilience.time_sync import time_sync_manager
            from agent.streaming.manager import agent_stream_manager

            active_streams = agent_stream_manager.list_active_streams()

            # Send initial state reconciliation
            reconcile_msg = {
                "type": "reconciliation",
                "agent_id": self.agent_id,
                "payload": {"active_streams": active_streams, "devices": []},
                "timestamp": time_sync_manager.get_compensated_iso(),
            }
            await ws.send(json.dumps(reconcile_msg))

            # Start heartbeat loop in background
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

            try:
                async for raw_msg in ws:
                    await self._handle_message(ws, str(raw_msg))
            finally:
                self._connected = False
                heartbeat_task.cancel()
                with contextlib.suppress(Exception):
                    await heartbeat_task

    async def run(self) -> None:
        """Persistent connection loop with backoff and reconnection."""
        self._running = True
        attempt = 0
        auth_failures = 0

        while self._running:
            try:
                await self.connect_once()
                attempt = 0  # Reset backoff on clean connection
                auth_failures = 0
            except ConnectionClosed as exc:
                if exc.code == 4003:
                    log.error("agent_revoked_by_hub_halting", agent_id=self.agent_id)
                    self._running = False
                    break
                if exc.code == 4001:
                    auth_failures += 1
                    # Retry-storm prevention on auth failure: back off significantly (up to 300s)
                    auth_delay = min(
                        300.0, 30.0 * (2 ** min(auth_failures, 4))
                    ) + secrets.SystemRandom().uniform(0, 2.0)
                    log.warning(
                        "agent_auth_failed_retry_storm_prevention",
                        agent_id=self.agent_id,
                        backoff_seconds=round(auth_delay, 2),
                        auth_failures=auth_failures,
                    )
                    await asyncio.sleep(auth_delay)
                    continue

                log.warning("agent_connection_closed", code=exc.code, reason=exc.reason)
            except Exception as exc:
                log.warning("agent_connection_error", error=str(exc))

            if not self._running:
                break

            attempt += 1
            backoff_delay = self.compute_backoff(attempt)
            log.info(
                "agent_reconnect_waiting", delay_seconds=round(backoff_delay, 2), attempt=attempt
            )
            await asyncio.sleep(backoff_delay)

    def stop(self) -> None:
        """Signal client to stop reconnecting."""
        self._running = False
        self._connected = False
