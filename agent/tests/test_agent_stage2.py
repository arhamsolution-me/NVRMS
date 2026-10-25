"""Stage 2 agent tests: Encrypted storage, command execution, and backoff with jitter."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.client import AgentClient
from agent.commands import execute_command
from agent.storage import SecureStorage


class TestSecureStorage:
    """Tests for encrypted credential storage."""

    def test_save_load_clear_cycle(self, tmp_path: Path) -> None:
        """Data saved to SecureStorage must decrypt accurately and clear cleanly."""
        storage = SecureStorage(base_dir=tmp_path)

        # Before saving, load returns None
        assert storage.load() is None

        # Save credentials
        creds = {
            "agent_id": "test-agent-uuid-1234",
            "agent_token": "agt_very_secret_token_value",
            "hub_url": "ws://localhost:8000",
            "name": "Warehouse Agent",
        }
        storage.save(creds)

        # File exists and is encrypted (cannot parse as plaintext JSON)
        raw_bytes = storage.file_path.read_bytes()
        assert b"agt_very_secret_token_value" not in raw_bytes

        # Decrypt and verify
        loaded = storage.load()
        assert loaded == creds

        # Clear
        storage.clear()
        assert storage.load() is None
        assert not storage.file_path.exists()

    def test_tampered_storage_returns_none(self, tmp_path: Path) -> None:
        """Tampered ciphertext must fail authentication and safely return None."""
        storage = SecureStorage(base_dir=tmp_path)
        storage.save({"key": "value"})

        # Corrupt file
        storage.file_path.write_bytes(b"tampered_corrupted_data_that_fails_hmac")
        assert storage.load() is None


class TestCommandProcessor:
    """Tests for agent local command execution and whitelist."""

    @pytest.mark.asyncio
    async def test_whitelisted_commands_execute(self) -> None:
        """ping, get_status, and reconcile_state must execute successfully."""
        ping_res = await execute_command("ping", {})
        assert ping_res["status"] == "pong"
        assert "timestamp" in ping_res

        status_res = await execute_command("get_status", {})
        assert status_res["status"] == "healthy"
        assert status_res["uptime_seconds"] >= 0

        reconcile_res = await execute_command("reconcile_state", {})
        assert "active_streams" in reconcile_res
        assert "devices" in reconcile_res

        probe_res = await execute_command("probe_nvr", {"ip": "192.168.1.100"})
        assert "status" in probe_res
        assert "diagnostics" in probe_res

        start_res = await execute_command("start_stream", {"stream_id": "s1"})
        assert start_res["status"] in ("started", "acknowledged")

        stop_res = await execute_command("stop_stream", {"stream_id": "s1"})
        assert stop_res["status"] in ("stopped", "acknowledged")

    @pytest.mark.asyncio
    async def test_non_whitelisted_command_rejected(self) -> None:
        """Commands outside the whitelist must raise ValueError."""
        with pytest.raises(ValueError, match="whitelist"):
            await execute_command("unauthorized_shell_command", {})


class TestReconnectionBackoff:
    """Tests for exponential backoff and jitter calculations."""

    def test_backoff_increases_exponentially_with_jitter_bounds(self) -> None:
        """Backoff delay must increase with attempts and stay within jitter limits."""
        client = AgentClient(
            agent_id="test",
            agent_token="token",
            hub_url="ws://localhost:8000",
            base_delay=1.0,
            max_delay=60.0,
        )

        for attempt in range(1, 5):
            delay = client.compute_backoff(attempt)
            assert delay >= client.base_delay
            assert delay <= client.max_delay

        # At attempt 10, delay should be capped near max_delay with jitter
        high_delay = client.compute_backoff(10)
        assert high_delay <= client.max_delay * 1.3


class TestAgentClientWorkflow:
    """Tests for agent client communication and enrolment functions."""

    def test_ws_url_formatting(self) -> None:
        """WebSocket URL is formatted correctly from http or https hub URL."""
        client = AgentClient(
            agent_id="agt-123",
            agent_token="tok-456",
            hub_url="http://hub.example.com:8000/",
        )
        url = client.get_ws_url()
        assert url == "ws://hub.example.com:8000/ws/agent?agent_id=agt-123&token=tok-456"

        client_ssl = AgentClient(
            agent_id="agt-123",
            agent_token="tok-456",
            hub_url="https://secure.example.com",
        )
        assert client_ssl.get_ws_url().startswith("wss://secure.example.com/ws/agent")

    @pytest.mark.asyncio
    async def test_enrol_agent_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """enrol_agent sends payload and returns credentials."""
        import httpx

        from agent.client import enrol_agent

        class MockResponse:
            status_code = 200

            def json(self) -> dict[str, str]:
                return {"agent_id": "test-id", "agent_token": "agt_token123"}

        async def mock_post(*args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        res = await enrol_agent("http://localhost:8000", "ENROL-CODE-123", "Test Agent")
        assert res["agent_id"] == "test-id"
        assert res["agent_token"] == "agt_token123"

    @pytest.mark.asyncio
    async def test_enrol_agent_failure_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """enrol_agent raises RuntimeError on non-200 responses."""
        import httpx

        from agent.client import enrol_agent

        class MockResponse:
            status_code = 400
            text = "Token expired"

            def json(self) -> dict[str, str]:
                return {"detail": "Token expired"}

        async def mock_post(*args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        with pytest.raises(RuntimeError, match="Token expired"):
            await enrol_agent("http://localhost:8000", "ENROL-EXPIRED")

    @pytest.mark.asyncio
    async def test_client_handle_command_and_heartbeat(self) -> None:
        """_handle_message processes commands and sends responses."""
        import json

        sent_messages: list[str] = []

        class MockWS:
            async def send(self, msg: str) -> None:
                sent_messages.append(msg)

        client = AgentClient(
            agent_id="agt-1",
            agent_token="tok-1",
            hub_url="http://localhost:8000",
        )
        mock_ws = MockWS()

        # 1. Valid command
        cmd_msg = json.dumps(
            {
                "type": "command",
                "command_id": "cmd-001",
                "command": "ping",
                "payload": {},
            }
        )
        await client._handle_message(mock_ws, cmd_msg)  # type: ignore[arg-type]
        assert len(sent_messages) == 1
        res = json.loads(sent_messages[0])
        assert res["type"] == "command_result"
        assert res["command_id"] == "cmd-001"
        assert res["status"] == "success"
        assert res["result"]["status"] == "pong"

        # 2. Invalid command
        bad_cmd = json.dumps(
            {
                "type": "command",
                "command_id": "cmd-002",
                "command": "dangerous_reboot",
                "payload": {},
            }
        )
        await client._handle_message(mock_ws, bad_cmd)  # type: ignore[arg-type]
        assert len(sent_messages) == 2
        bad_res = json.loads(sent_messages[1])
        assert bad_res["status"] == "error"

        # 3. Heartbeat ack (should not raise)
        ack_msg = json.dumps({"type": "heartbeat_ack", "timestamp": "2026-10-25T12:00:00Z"})
        await client._handle_message(mock_ws, ack_msg)  # type: ignore[arg-type]

        # 4. Stop client
        client.stop()
        assert not client._running
        assert not client._connected
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_client_heartbeat_loop(self) -> None:
        """_heartbeat_loop sends periodic heartbeat messages."""
        import asyncio
        import json

        sent_messages: list[str] = []

        class MockWS:
            async def send(self, msg: str) -> None:
                sent_messages.append(msg)

        client = AgentClient(
            agent_id="agt-hb-1",
            agent_token="tok-hb-1",
            hub_url="http://localhost:8000",
            heartbeat_interval=0.01,
        )
        client._running = True
        client._connected = True
        mock_ws = MockWS()

        task = asyncio.create_task(client._heartbeat_loop(mock_ws))  # type: ignore[arg-type]
        await asyncio.sleep(0.03)
        import contextlib

        client.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert len(sent_messages) >= 1
        hb = json.loads(sent_messages[0])
        assert hb["type"] == "heartbeat"
        assert hb["agent_id"] == "agt-hb-1"
