"""TLS Certificate Pinning verification for Edge Agent."""

from __future__ import annotations

import hashlib
import hmac

from agent.logging_config import get_logger

log = get_logger(__name__)


class CertificatePinningError(Exception):
    """Raised when the remote server TLS certificate fingerprint does not match the pinned hash."""


class CertificatePinningVerifier:
    """Verifies that the peer certificate matches a trusted SHA-256 fingerprint."""

    def __init__(self, pinned_fingerprint_sha256: str | None = None) -> None:
        self.pinned_fingerprint = (
            pinned_fingerprint_sha256.lower().replace(":", "").replace(" ", "")
            if pinned_fingerprint_sha256
            else None
        )

    def compute_fingerprint(self, cert_der: bytes) -> str:
        """Compute colon-less lowercase hex SHA-256 fingerprint from DER certificate bytes."""
        return hashlib.sha256(cert_der).hexdigest().lower()

    def verify_cert_der(self, cert_der: bytes) -> bool:
        """Verify the DER certificate against the pinned fingerprint.

        Returns:
            True if valid.

        Raises:
            CertificatePinningError if fingerprint does not match.
        """
        if not self.pinned_fingerprint:
            # Pinning not enabled / not configured
            return True

        actual_fingerprint = self.compute_fingerprint(cert_der)
        if not hmac.compare_digest(actual_fingerprint, self.pinned_fingerprint):
            log.error(
                "certificate_pinning_failed_mismatch",
                expected=self.pinned_fingerprint,
                actual=actual_fingerprint,
            )
            raise CertificatePinningError(
                f"TLS certificate pinning mismatch! Expected {self.pinned_fingerprint}, got {actual_fingerprint}"
            )

        log.debug("certificate_pinning_verified", fingerprint=actual_fingerprint)
        return True
