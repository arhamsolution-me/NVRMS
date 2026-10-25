"""Stage 3 agent tests: SSRF protection, reachability diagnostics, templates, encoding, and lockout."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.discovery.nvr_probe import (
    LOCKOUT_TRACKER,
    build_rtsp_url,
    check_and_update_lockout,
    check_tcp_port,
    load_templates,
    probe_nvr,
    record_auth_failure,
)
from agent.discovery.ssrf import SSRFSecurityError, validate_target_ip
from agent.storage import SecureStorage


class TestSSRFGuard:
    """Tests for SSRF IP constraints."""

    def test_private_ips_allowed(self) -> None:
        """RFC 1918 and loopback IPs are allowed."""
        assert validate_target_ip("192.168.1.100") == "192.168.1.100"
        assert validate_target_ip("10.0.0.1") == "10.0.0.1"
        assert validate_target_ip("172.16.0.5") == "172.16.0.5"
        assert validate_target_ip("127.0.0.1") == "127.0.0.1"

    def test_public_ips_rejected(self) -> None:
        """Public internet IPs must be rejected."""
        with pytest.raises(SSRFSecurityError, match="allowed private"):
            validate_target_ip("8.8.8.8")

        with pytest.raises(SSRFSecurityError, match="allowed private"):
            validate_target_ip("1.1.1.1")

    def test_cloud_metadata_rejected(self) -> None:
        """Cloud metadata endpoints (169.254.169.254) must be strictly forbidden."""
        with pytest.raises(SSRFSecurityError, match="forbidden network"):
            validate_target_ip("169.254.169.254")

        with pytest.raises(SSRFSecurityError, match="forbidden network"):
            validate_target_ip("169.254.1.1")

    def test_multicast_and_broadcast_rejected(self) -> None:
        """Multicast and broadcast IPs must be rejected."""
        with pytest.raises(SSRFSecurityError):
            validate_target_ip("224.0.0.1")

        with pytest.raises(SSRFSecurityError):
            validate_target_ip("255.255.255.255")

    def test_empty_host_rejected(self) -> None:
        """Empty input raises SSRFSecurityError."""
        with pytest.raises(SSRFSecurityError, match="empty"):
            validate_target_ip("   ")


class TestRTSPUrlBuilder:
    """Tests for safe URL-encoding and template path substitutions."""

    def test_special_characters_encoded_properly(self) -> None:
        """Special characters in username/password must be percent-encoded."""
        user = "admin@local"
        password = "P@ss:w/ord#123?&="
        url = build_rtsp_url(
            ip="192.168.1.50",
            port=554,
            username=user,
            password=password,
            path_template="/Streaming/Channels/{channel}01",
            channel=2,
        )
        assert "@local" not in url.split("@")[0]  # @ in username must be encoded
        assert "admin%40local" in url
        assert "P%40ss%3Aw%2Ford%23123%3F%26%3D" in url
        assert url.endswith("/Streaming/Channels/201")

    def test_no_credentials_url(self) -> None:
        """Empty credentials produce clean URL without @ sign."""
        url = build_rtsp_url(
            ip="192.168.1.50",
            port=554,
            username="",
            password="",
            path_template="/ch{channel}/main",
            channel=1,
        )
        assert "@" not in url
        assert url == "rtsp://192.168.1.50:554/ch1/main"


class TestReachabilityAndLockout:
    """Tests for TCP diagnostics and brute-force lockout protection."""

    @pytest.mark.asyncio
    async def test_reachability_on_closed_port(self) -> None:
        """Probing an unreachable port returns structured reachability error."""
        reachable, msg = await check_tcp_port("127.0.0.1", 59999, timeout=0.2)
        assert not reachable
        assert "59999" in msg

    @pytest.mark.asyncio
    async def test_reachability_on_open_port(self) -> None:
        """Probing an active server port succeeds."""
        # Start a local TCP server
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        reachable, msg = await check_tcp_port("127.0.0.1", port, timeout=1.0)
        server.close()
        await server.wait_closed()

        assert reachable
        assert "reachable" in msg.lower()

    def test_lockout_trigger(self) -> None:
        """3 consecutive failures triggers lockout protection."""
        ip = "192.168.10.99"
        port = 554
        LOCKOUT_TRACKER.pop((ip, port), None)

        assert not check_and_update_lockout(ip, port)
        record_auth_failure(ip, port)
        record_auth_failure(ip, port)
        assert not check_and_update_lockout(ip, port)

        record_auth_failure(ip, port)
        # 3rd failure locks out
        assert check_and_update_lockout(ip, port)


class TestVendorTemplatesAndProbe:
    """Tests for vendor templates loading and probe execution."""

    def test_vendor_templates_exist(self) -> None:
        """All major brands exist in vendor templates."""
        templates = load_templates()
        assert "hikvision" in templates
        assert "dahua" in templates
        assert "uniview" in templates
        assert "hanwha" in templates
        assert "axis" in templates
        assert "xiongmai" in templates
        assert "generic" in templates

    @pytest.mark.asyncio
    async def test_probe_nvr_full_flow(self) -> None:
        """Probe against active socket enumerates channels with structured metadata."""
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        result = await probe_nvr(
            ip="127.0.0.1",
            port=port,
            username="admin",
            password="password123!",
            brand="hikvision",
            channels_to_probe=4,
        )
        server.close()
        await server.wait_closed()

        assert result["status"] == "success"
        assert result["brand"] == "hikvision"
        assert result["channel_count"] == 4
        assert len(result["channels"]) == 4

        # Channel 1 checks
        ch1 = result["channels"][0]
        assert ch1["channel_number"] == 1
        assert "Streaming/Channels/101" in ch1["main_stream_url"]
        assert "Streaming/Channels/102" in ch1["sub_stream_url"]

    @pytest.mark.asyncio
    async def test_probe_nvr_ssrf_rejection(self) -> None:
        """Probe to public IP is immediately rejected."""
        with pytest.raises(SSRFSecurityError):
            await probe_nvr(ip="8.8.8.8", port=554)


class TestEncryptedNVRVault:
    """Tests for storing NVR credentials encrypted on agent."""

    def test_save_and_retrieve_nvr_credentials(self, tmp_path: Path) -> None:
        """NVR credentials are saved and decrypted without plaintext exposure."""
        storage = SecureStorage(base_dir=tmp_path)
        storage.save_nvr_credentials(
            nvr_id="nvr-uuid-001",
            creds={"username": "admin", "password": "SuperSecretNVRPassword!"},
        )

        # Raw file does not contain plaintext password
        raw = storage.file_path.read_bytes()
        assert b"SuperSecretNVRPassword!" not in raw

        # Loaded credentials match
        loaded = storage.get_nvr_credentials("nvr-uuid-001")
        assert loaded is not None
        assert loaded["password"] == "SuperSecretNVRPassword!"
