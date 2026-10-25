"""Tests for Agent security hardening and certificate pinning."""

from __future__ import annotations

import hashlib

import pytest

from agent.security.pinning import CertificatePinningError, CertificatePinningVerifier


class TestCertificatePinning:
    """Certificate pinning and MITM rejection tests."""

    def test_matching_fingerprint_verifies_successfully(self) -> None:
        cert_der = b"dummy_mock_x509_der_certificate_data_123"
        sha = hashlib.sha256(cert_der).hexdigest()

        verifier = CertificatePinningVerifier(pinned_fingerprint_sha256=sha)
        assert verifier.verify_cert_der(cert_der) is True

    def test_mismatched_fingerprint_raises_pinning_error(self) -> None:
        cert_der = b"dummy_mock_x509_der_certificate_data_123"
        rogue_cert = b"attacker_mitm_proxy_certificate_data_999"

        expected_sha = hashlib.sha256(cert_der).hexdigest()
        verifier = CertificatePinningVerifier(pinned_fingerprint_sha256=expected_sha)

        with pytest.raises(CertificatePinningError, match="pinning mismatch"):
            verifier.verify_cert_der(rogue_cert)

    def test_disabled_pinning_allows_any_cert(self) -> None:
        verifier = CertificatePinningVerifier(pinned_fingerprint_sha256=None)
        assert verifier.verify_cert_der(b"any_random_bytes") is True

    def test_fingerprint_normalization_handles_colons_and_caps(self) -> None:
        cert_der = b"sample_certificate"
        raw_sha = hashlib.sha256(cert_der).hexdigest().upper()
        # Format with colons: AA:BB:CC:...
        formatted_sha = ":".join(raw_sha[i : i + 2] for i in range(0, len(raw_sha), 2))

        verifier = CertificatePinningVerifier(pinned_fingerprint_sha256=formatted_sha)
        assert verifier.verify_cert_der(cert_der) is True
