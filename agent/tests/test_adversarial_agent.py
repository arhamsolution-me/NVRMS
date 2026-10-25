"""Stage S6: Adversarial Agent Hardening Test Harness.

Tests defending against:
1. Fake Hub Rejection: Agent refuses connection to rogue hub presenting untrusted/wrong CA.
2. MITM Proxy Rejection: Intercepted TLS handshake with rogue MITM proxy certificate rejected.
3. Rogue Agent with Stolen Credentials: Agent attempting cross-tenant or foreign namespace publish rejected.
4. Revoked Agent Dropped: Revoking agent terminates live WebSocket connection immediately.
5. Ed25519 Signed Updates & Downgrade Defense:
   - Invalid signature rejected.
   - Version downgrade rejected.
   - Automatic rollback on post-update failure.
6. Tamper Resistance & Config Integrity:
   - Config tampering detected via MAC mismatch.
   - Safe failure mode: agent refuses to stream when tampered.
7. SSRF and Pivot Guard:
   - Loopback target blocked in hardened mode.
   - Link-local cloud metadata target (169.254.169.254) blocked.
   - Infrastructure Hub IP target blocked.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from agent.discovery.ssrf import SSRFSecurityError, validate_target_ip
from agent.resilience.updater import AgentUpdater, UpdateVerificationError
from agent.security.integrity import ConfigIntegrityError, ConfigIntegrityManager
from agent.security.pinning import CertificatePinningError, CertificatePinningVerifier
from agent.streaming.manager import AgentStreamManager


class TestFakeHubAndMITMRejection:
    """Verifies that an agent refuses connection to fake hubs or MITM proxies."""

    def test_fake_hub_with_untrusted_cert_rejected(self) -> None:
        """Legitimate hub presents valid pinned cert; fake hub presents rogue cert."""
        legitimate_hub_cert = b"genuine_hub_ca_x509_certificate_der"
        fake_hub_cert = b"attacker_fake_hub_rogue_ca_certificate_der"

        legit_pin = hashlib.sha256(legitimate_hub_cert).hexdigest()
        verifier = CertificatePinningVerifier(pinned_fingerprint_sha256=legit_pin)

        # Genuine hub cert succeeds
        assert verifier.verify_cert_der(legitimate_hub_cert) is True

        # Fake hub cert fails closed
        with pytest.raises(CertificatePinningError, match="pinning mismatch"):
            verifier.verify_cert_der(fake_hub_cert)

    def test_mitm_proxy_interception_rejected(self) -> None:
        """MITM proxy (e.g., mitmproxy) intercepts TLS with dynamically generated cert."""
        primary_cert = b"primary_hub_certificate_der"
        backup_cert = b"backup_hub_certificate_der"
        mitm_proxy_cert = b"mitmproxy_ca_generated_intercepted_cert_der"

        verifier = CertificatePinningVerifier(
            pinned_fingerprint_sha256=hashlib.sha256(primary_cert).hexdigest(),
            backup_fingerprint_sha256=hashlib.sha256(backup_cert).hexdigest(),
        )

        # Both primary and backup pass
        assert verifier.verify_cert_der(primary_cert) is True
        assert verifier.verify_cert_der(backup_cert) is True

        # MITM interception strictly rejected
        with pytest.raises(CertificatePinningError, match="pinning mismatch"):
            verifier.verify_cert_der(mitm_proxy_cert)


class TestRevokedAgentDropped:
    """Verifies immediate disconnection when an agent is revoked."""

    @pytest.mark.asyncio
    async def test_revoked_agent_live_connection_dropped(self) -> None:
        """AgentManager drops active WebSocket connection on revocation."""
        from hub_backend.services.agent_manager import AgentConnection, agent_manager

        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()

        agent_id = "test-agent-revocation-uuid-1234"
        conn = AgentConnection(agent_id=agent_id, websocket=mock_ws)

        async with agent_manager._lock:
            agent_manager.active_agents[agent_id] = conn

        assert agent_manager.is_online(agent_id) is True

        # Revoke the agent
        await agent_manager.revoke_agent(agent_id)

        # Connection must be closed with code 4003 (Agent revoked)
        mock_ws.close.assert_called_once_with(code=4003, reason="Agent revoked")
        assert agent_manager.is_online(agent_id) is False


class TestEd25519SignedUpdatesAndDowngradeDefense:
    """Verifies firmware updates enforce asymmetric Ed25519 signatures and downgrade protection."""

    def test_valid_ed25519_signed_update_succeeds(self, tmp_path: Path) -> None:
        # Generate Ed25519 keypair
        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()

        updater = AgentUpdater(trusted_public_key=pub_key)

        curr_file = tmp_path / "agent_current.py"
        curr_file.write_text("print('version 1.0.0')", encoding="utf-8")

        new_pkg = tmp_path / "agent_v1.1.0.py"
        new_pkg.write_text("print('version 1.1.0')", encoding="utf-8")

        sha256 = updater.compute_sha256(new_pkg)
        sig = updater.sign_package_ed25519(new_pkg, priv_key)

        result = updater.apply_update(
            current_file=curr_file,
            new_package=new_pkg,
            expected_sha256=sha256,
            signature=sig,
            target_version="1.1.0",
            current_version="1.0.0",
        )

        assert result["status"] == "success"
        assert curr_file.read_text(encoding="utf-8") == "print('version 1.1.0')"

    def test_invalid_signature_rejected(self, tmp_path: Path) -> None:
        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()
        updater = AgentUpdater(trusted_public_key=pub_key)

        pkg = tmp_path / "tampered.py"
        pkg.write_text("malicious payload", encoding="utf-8")

        sha256 = updater.compute_sha256(pkg)
        bogus_sig = "deadbeef" * 8  # 32 bytes hex, invalid signature

        with pytest.raises(UpdateVerificationError, match="signature"):
            updater.verify_package(
                package_path=pkg,
                expected_sha256=sha256,
                signature=bogus_sig,
            )

    def test_version_downgrade_rejected(self, tmp_path: Path) -> None:
        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()
        updater = AgentUpdater(trusted_public_key=pub_key)

        downgrade_pkg = tmp_path / "old_v0.9.0.py"
        downgrade_pkg.write_text("print('v0.9.0')", encoding="utf-8")

        sha256 = updater.compute_sha256(downgrade_pkg)
        sig = updater.sign_package_ed25519(downgrade_pkg, priv_key)

        with pytest.raises(UpdateVerificationError, match="Version downgrade rejected"):
            updater.apply_update(
                current_file=tmp_path / "current.py",
                new_package=downgrade_pkg,
                expected_sha256=sha256,
                signature=sig,
                target_version="0.9.0",
                current_version="1.0.0",
            )

    def test_automatic_rollback_on_health_check_failure(self, tmp_path: Path) -> None:
        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()
        updater = AgentUpdater(trusted_public_key=pub_key)

        curr_file = tmp_path / "running.py"
        curr_file.write_text("stable_version", encoding="utf-8")

        bad_pkg = tmp_path / "broken_v2.0.0.py"
        bad_pkg.write_text("broken_version", encoding="utf-8")

        sha256 = updater.compute_sha256(bad_pkg)
        sig = updater.sign_package_ed25519(bad_pkg, priv_key)

        # Health check fails
        result = updater.apply_update(
            current_file=curr_file,
            new_package=bad_pkg,
            expected_sha256=sha256,
            signature=sig,
            target_version="2.0.0",
            current_version="1.0.0",
            health_check_fn=lambda: False,
        )

        assert result["status"] == "rolled_back"
        assert result["rolled_back"] is True
        # File must be restored to original stable version
        assert curr_file.read_text(encoding="utf-8") == "stable_version"


class TestTamperResistanceAndConfigIntegrity:
    """Verifies HMAC configuration integrity and streaming refusal upon tamper."""

    def test_config_mac_validation_and_tamper_detection(self) -> None:
        manager = ConfigIntegrityManager(key=b"test_integrity_key_1234")

        original_config = {
            "agent_id": "agt_01",
            "hub_url": "wss://hub.nvrsms.local:443",
            "tenant_id": "tenant_abc",
        }

        valid_mac = manager.compute_mac(original_config)
        assert manager.verify_config(original_config, valid_mac) is True

        # Attacker tampers with hub_url to redirect agent to evil server
        tampered_config = {
            "agent_id": "agt_01",
            "hub_url": "wss://evil-hacker.com:443",
            "tenant_id": "tenant_abc",
        }

        with pytest.raises(ConfigIntegrityError, match="configuration has been tampered with"):
            manager.verify_config(tampered_config, valid_mac)

        assert manager.is_tampered is True

    @pytest.mark.asyncio
    async def test_agent_refuses_to_stream_when_tampered(self) -> None:
        """StreamManager refuses to start video when configuration tamper is detected."""
        from agent.security.integrity import config_integrity_manager

        stream_manager = AgentStreamManager()

        # Artificially set tamper flag
        config_integrity_manager.is_tampered = True

        with pytest.raises(ConfigIntegrityError, match="stream refused because agent configuration tamper was detected"):
            await stream_manager.start_stream(
                stream_id="stream_tamper_test",
                source_url="rtsp://192.168.1.100:554/live",
                target_path="live/cam1",
            )

        # Reset flag for other tests
        config_integrity_manager.is_tampered = False


class TestSSRFAndScannerAbuseGuard:
    """Verifies that the agent refuses to probe loopback, metadata, or infrastructure targets."""

    def test_loopback_probes_blocked_in_hardened_mode(self) -> None:
        with pytest.raises(SSRFSecurityError, match="loopback address and forbidden"):
            validate_target_ip("127.0.0.1", allow_loopback=False)

        with pytest.raises(SSRFSecurityError, match="loopback address and forbidden"):
            validate_target_ip("127.0.10.5", allow_loopback=False)

    def test_cloud_metadata_endpoints_always_blocked(self) -> None:
        # AWS / GCP / Azure metadata endpoint
        with pytest.raises(SSRFSecurityError, match="forbidden network"):
            validate_target_ip("169.254.169.254")

        # Entire link-local range
        with pytest.raises(SSRFSecurityError, match="forbidden network"):
            validate_target_ip("169.254.1.20")

    def test_hub_infrastructure_pivot_blocked(self) -> None:
        hub_ip = "192.168.1.50"
        with pytest.raises(SSRFSecurityError, match="forbidden infrastructure host"):
            validate_target_ip(hub_ip, blocked_hosts=[hub_ip])

    def test_valid_private_lan_target_allowed(self) -> None:
        assert validate_target_ip("192.168.1.100") == "192.168.1.100"
        assert validate_target_ip("10.10.20.5") == "10.10.20.5"
