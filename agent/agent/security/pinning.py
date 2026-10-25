"""TLS Certificate Pinning verification for Edge Agent with primary and backup pin rotation."""

from __future__ import annotations

import hashlib
import hmac

from agent.logging_config import get_logger

log = get_logger(__name__)


class CertificatePinningError(Exception):
    """Raised when the remote server TLS certificate fingerprint does not match any pinned hash."""


class CertificatePinningVerifier:
    """Verifies that the peer certificate matches trusted primary or backup SHA-256 fingerprints."""

    def __init__(
        self,
        pinned_fingerprint_sha256: str | None = None,
        backup_fingerprint_sha256: str | None = None,
        additional_pins: list[str] | None = None,
    ) -> None:
        self.pinned_fingerprints: set[str] = set()
        if pinned_fingerprint_sha256:
            self.pinned_fingerprints.add(self._normalize(pinned_fingerprint_sha256))
        if backup_fingerprint_sha256:
            self.pinned_fingerprints.add(self._normalize(backup_fingerprint_sha256))
        if additional_pins:
            for pin in additional_pins:
                if pin:
                    self.pinned_fingerprints.add(self._normalize(pin))

    @staticmethod
    def _normalize(pin: str) -> str:
        return pin.lower().replace(":", "").replace(" ", "").strip()

    @property
    def pinned_fingerprint(self) -> str | None:
        """For backward compatibility: returns one of the pinned fingerprints or None."""
        return next(iter(self.pinned_fingerprints)) if self.pinned_fingerprints else None

    def compute_fingerprint(self, cert_der: bytes) -> str:
        """Compute colon-less lowercase hex SHA-256 fingerprint from DER certificate bytes."""
        return hashlib.sha256(cert_der).hexdigest().lower()

    def verify_cert_der(self, cert_der: bytes) -> bool:
        """Verify the DER certificate against the pinned fingerprints.

        Returns:
            True if certificate fingerprint matches primary or backup pin.

        Raises:
            CertificatePinningError if fingerprint does not match any trusted pin.
        """
        if not self.pinned_fingerprints:
            # Pinning not enabled / not configured
            return True

        actual_fingerprint = self.compute_fingerprint(cert_der)
        for trusted_pin in self.pinned_fingerprints:
            if hmac.compare_digest(actual_fingerprint, trusted_pin):
                log.debug("certificate_pinning_verified", fingerprint=actual_fingerprint)
                return True

        log.error(
            "certificate_pinning_failed_mismatch",
            expected=list(self.pinned_fingerprints),
            actual=actual_fingerprint,
        )
        raise CertificatePinningError(
            f"TLS certificate pinning mismatch! Expected one of {list(self.pinned_fingerprints)}, got {actual_fingerprint}"
        )
