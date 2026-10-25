"""Tests for Edge Agent observability and diagnostics redaction."""

from __future__ import annotations

import json

import pytest

from agent.commands import execute_command
from agent.diagnostics import diagnostics_collector


class TestAgentDiagnosticsAndRedaction:
    """Tests for system diagnostics bundle and credential sanitization."""

    def test_diagnostics_bundle_structure(self) -> None:
        bundle = diagnostics_collector.collect_bundle()
        assert "timestamp" in bundle
        assert "agent_version" in bundle
        assert "system" in bundle
        assert "disk" in bundle
        assert "time_sync" in bundle
        assert "active_streams" in bundle
        assert "config" in bundle

    def test_rtsp_credentials_redaction(self) -> None:
        raw_url = "rtsp://admin:P@ssw0rd123!@192.168.1.50:554/Streaming/Channels/101"
        cleaned = diagnostics_collector.sanitize_string(raw_url)
        assert "P@ssw0rd123!" not in cleaned
        assert "admin" not in cleaned
        assert (
            cleaned
            == "rtsp://***REDACTED***:***REDACTED***@192.168.1.50:554/Streaming/Channels/101"
        )

    def test_jwt_and_bearer_token_redaction(self) -> None:
        raw_jwt = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        cleaned = diagnostics_collector.sanitize_string(raw_jwt)
        assert "eyJhbGci" not in cleaned
        assert "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c" not in cleaned
        assert "***REDACTED***" in cleaned

    def test_recursive_dict_secret_redaction(self) -> None:
        dirty_payload = {
            "name": "Branch Agent",
            "auth": {
                "password": "CleartextPassword99!",
                "agent_token": "agt_live_secret_token_12345",
                "nested": {
                    "private_key": "-----BEGIN PRIVATE KEY-----MIIEvgIBADANBgk...",
                    "safe_field": "public_data_value",
                },
            },
            "streams": [
                {"url": "rtsp://camera_user:CameraSecret@192.168.1.100/ch1"},
            ],
        }

        sanitized = diagnostics_collector.sanitize_data(dirty_payload)
        dumped = json.dumps(sanitized)

        # None of the secrets must be present
        assert "CleartextPassword99!" not in dumped
        assert "agt_live_secret_token_12345" not in dumped
        assert "BEGIN PRIVATE KEY" not in dumped
        assert "CameraSecret" not in dumped
        # Safe fields remain
        assert sanitized["auth"]["nested"]["safe_field"] == "public_data_value"

    @pytest.mark.asyncio
    async def test_get_diagnostics_command_dispatch(self) -> None:
        res = await execute_command("get_diagnostics", {})
        assert "system" in res
        assert "agent_version" in res
