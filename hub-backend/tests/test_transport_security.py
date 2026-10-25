"""Stage S2 Tests: Transport Security, mTLS, Internal CA, Pinning, and TURN Hardening."""

from __future__ import annotations

import hashlib
import time
import uuid

import pytest
from agent.client import AgentClient, enrol_agent
from agent.security.pinning import CertificatePinningError, CertificatePinningVerifier
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from hub_backend.security.ca import InternalCA
from hub_backend.security.turn import generate_turn_credentials, verify_turn_credentials


class TestInternalCAAndMutualTLS:
    """Tests for Central Hub internal Certificate Authority and mTLS certificate verification."""

    def test_internal_ca_root_and_client_issuance(self) -> None:
        """Root CA is valid self-signed CA, issues valid agent client certificates."""
        ca = InternalCA()
        assert ca.ca_cert.serial_number > 0
        assert ca.ca_cert.issuer == ca.ca_cert.subject
        assert len(ca.ca_fingerprint_sha256) == 64

        agent_id = uuid.uuid4()
        creds = ca.issue_agent_certificate(agent_id=agent_id, validity_days=90)

        assert "client_cert_pem" in creds
        assert "client_key_pem" in creds
        assert creds["ca_fingerprint_sha256"] == ca.ca_fingerprint_sha256

        # Verify cert with expected agent ID
        is_valid = ca.verify_agent_certificate(
            cert_pem=creds["client_cert_pem"],
            expected_agent_id=agent_id,
        )
        assert is_valid is True

    def test_client_cert_cn_mismatch_rejected(self) -> None:
        """Certificate issued for agent-A is rejected when presented by agent-B."""
        ca = InternalCA()
        agent_a = uuid.uuid4()
        agent_b = uuid.uuid4()

        creds_a = ca.issue_agent_certificate(agent_id=agent_a)
        is_valid = ca.verify_agent_certificate(
            cert_pem=creds_a["client_cert_pem"],
            expected_agent_id=agent_b,
        )
        assert is_valid is False

    def test_rogue_ca_certificate_rejected(self) -> None:
        """Certificate signed by an untrusted rogue CA is rejected."""
        legit_ca = InternalCA()
        rogue_ca = InternalCA()

        agent_id = uuid.uuid4()
        rogue_creds = rogue_ca.issue_agent_certificate(agent_id=agent_id)

        # Legit CA must reject rogue cert
        is_valid = legit_ca.verify_agent_certificate(
            cert_pem=rogue_creds["client_cert_pem"],
            expected_agent_id=agent_id,
        )
        assert is_valid is False

    def test_revoked_certificate_rejected(self) -> None:
        """Revoking an agent certificate immediately fails verification."""
        ca = InternalCA()
        agent_id = uuid.uuid4()
        creds = ca.issue_agent_certificate(agent_id=agent_id)
        serial = int(creds["serial_number"])

        assert (
            ca.verify_agent_certificate(creds["client_cert_pem"], expected_agent_id=agent_id)
            is True
        )

        ca.revoke_certificate(serial)
        assert (
            ca.verify_agent_certificate(creds["client_cert_pem"], expected_agent_id=agent_id)
            is False
        )


class TestCertificatePinningAndRotation:
    """Tests for Edge Agent certificate pinning and zero-site-visit dual pin rotation."""

    def _generate_test_cert_der(self, cn: str) -> bytes:
        backend = default_backend()
        key = ec.generate_private_key(ec.SECP256R1(), backend)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        now = time.time()
        import datetime

        dt_now = datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(dt_now)
            .not_valid_after(dt_now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256(), backend)
        )
        return cert.public_bytes(serialization.Encoding.DER)

    def test_pinning_accepts_primary_pin(self) -> None:
        """Verifier accepts peer certificate matching primary pin."""
        cert_der = self._generate_test_cert_der("hub-primary.nvrsms.local")
        sha256 = hashlib.sha256(cert_der).hexdigest()

        verifier = CertificatePinningVerifier(pinned_fingerprint_sha256=sha256)
        assert verifier.verify_cert_der(cert_der) is True

    def test_zero_site_visit_rotation_accepts_backup_pin(self) -> None:
        """During rotation cutover, verifier accepts peer certificate matching backup pin."""
        primary_cert = self._generate_test_cert_der("hub-old.nvrsms.local")
        backup_cert = self._generate_test_cert_der("hub-new.nvrsms.local")

        primary_sha = hashlib.sha256(primary_cert).hexdigest()
        backup_sha = hashlib.sha256(backup_cert).hexdigest()

        verifier = CertificatePinningVerifier(
            pinned_fingerprint_sha256=primary_sha,
            backup_fingerprint_sha256=backup_sha,
        )

        # Both primary and backup certificates are accepted
        assert verifier.verify_cert_der(primary_cert) is True
        assert verifier.verify_cert_der(backup_cert) is True

    def test_rogue_ca_fails_closed_when_neither_pin_matches(self) -> None:
        """Rogue certificate matching neither primary nor backup pin is strictly rejected."""
        primary_cert = self._generate_test_cert_der("hub-legit.nvrsms.local")
        backup_cert = self._generate_test_cert_der("hub-backup.nvrsms.local")
        rogue_cert = self._generate_test_cert_der("rogue-mitm.attacker.com")

        verifier = CertificatePinningVerifier(
            pinned_fingerprint_sha256=hashlib.sha256(primary_cert).hexdigest(),
            backup_fingerprint_sha256=hashlib.sha256(backup_cert).hexdigest(),
        )

        with pytest.raises(CertificatePinningError, match="pinning mismatch"):
            verifier.verify_cert_der(rogue_cert)


class TestPlaintextTransportRefusal:
    """Tests that unencrypted HTTP / WS connections are refused in strict mode."""

    def test_agent_client_refuses_plaintext_ws(self) -> None:
        """AgentClient refuses ws:// when allow_insecure_transport is False."""
        client = AgentClient(
            agent_id=str(uuid.uuid4()),
            agent_token="agt_test",
            hub_url="http://hub.nvrsms.local:8000",
            allow_insecure_transport=False,
        )
        with pytest.raises(ValueError, match="Plaintext transport refused"):
            client.get_ws_url()

    @pytest.mark.asyncio
    async def test_enrol_agent_refuses_plaintext_http(self) -> None:
        """enrol_agent refuses http:// when allow_insecure_transport is False."""
        with pytest.raises(ValueError, match="Plaintext transport refused"):
            await enrol_agent(
                hub_url="http://hub.nvrsms.local",
                enrolment_code="ENROL-1234-5678",
                allow_insecure_transport=False,
            )


class TestTURNHardening:
    """Tests for coturn time-limited HMAC-SHA1 credential derivation and verification."""

    def test_generate_and_verify_turn_credentials(self) -> None:
        """Generated credentials match coturn format and verify successfully."""
        user_id = uuid.uuid4()
        creds = generate_turn_credentials(user_id=user_id, ttl_seconds=3600)

        assert "username" in creds
        assert "password" in creds
        assert "uris" in creds
        assert any(uri.startswith("turns:") for uri in creds["uris"])

        assert verify_turn_credentials(creds["username"], creds["password"]) is True

    def test_expired_turn_credentials_rejected(self) -> None:
        """Expired credentials are rejected."""
        user_id = uuid.uuid4()
        # Create credential that expired 10 minutes ago
        creds = generate_turn_credentials(user_id=user_id, ttl_seconds=-600)
        assert verify_turn_credentials(creds["username"], creds["password"]) is False

    def test_tampered_turn_password_rejected(self) -> None:
        """Tampered password fails HMAC verification."""
        user_id = uuid.uuid4()
        creds = generate_turn_credentials(user_id=user_id, ttl_seconds=3600)
        assert verify_turn_credentials(creds["username"], "tampered_password_123") is False


class TestConfigSecurityGuards:
    """Tests verifying Caddyfile and coturn configurations enforce modern TLS and anti-relay."""

    def test_caddyfile_modern_tls_and_hsts(self) -> None:
        """Caddyfile enforces TLS 1.2+ AEAD and HSTS preload."""
        from pathlib import Path

        workspace_root = Path(__file__).resolve().parents[2]
        caddyfile_path = workspace_root / "media" / "Caddyfile"
        with open(caddyfile_path, encoding="utf-8") as f:
            content = f.read()

        assert "protocols tls1.2 tls1.3" in content
        assert "Strict-Transport-Security" in content
        assert "preload" in content
        assert "ciphers" in content
        # Ensure no weak ciphers
        assert "3DES" not in content
        assert "RC4" not in content
        assert "MD5" not in content

    def test_coturn_config_hardening(self) -> None:
        """coturn config disables open relay, enforces auth secret, and blocks private IP targets."""
        from pathlib import Path

        workspace_root = Path(__file__).resolve().parents[2]
        turn_config_path = workspace_root / "infra" / "coturn" / "turnserver.conf"
        with open(turn_config_path, encoding="utf-8") as f:
            content = f.read()

        assert "use-auth-secret" in content
        assert "no-multicast-peers" in content
        assert "denied-peer-ip=127.0.0.0-127.255.255.255" in content
        assert "denied-peer-ip=169.254.0.0-169.254.255.255" in content
        assert "cipher-list" in content
        assert "tls-listening-port=5349" in content
