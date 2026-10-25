"""Agent Tamper Resistance and Configuration Integrity (MAC) Verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from agent.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_INTEGRITY_KEY = b"nvrsms_agent_config_integrity_mac_key_2026"


class ConfigIntegrityError(Exception):
    """Raised when configuration tampering or MAC validation failure is detected."""


class ConfigIntegrityManager:
    """Verifies configuration integrity and enforces fail-closed tamper defense."""

    def __init__(self, key: bytes = DEFAULT_INTEGRITY_KEY) -> None:
        self.key = key
        self.is_tampered: bool = False

    def canonicalize(self, data: dict[str, Any]) -> bytes:
        """Produce canonical JSON representation of configuration dict."""
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def compute_mac(self, config_dict: dict[str, Any]) -> str:
        """Compute HMAC-SHA256 MAC over configuration state."""
        payload = self.canonicalize(config_dict)
        return hmac.new(self.key, payload, hashlib.sha256).hexdigest()

    def verify_config(self, config_dict: dict[str, Any], expected_mac: str) -> bool:
        """Verify configuration against expected MAC signature.

        Raises:
            ConfigIntegrityError: If MAC does not match or parsing fails.
        """
        actual_mac = self.compute_mac(config_dict)
        if not hmac.compare_digest(actual_mac.lower(), expected_mac.lower()):
            self.is_tampered = True
            log.critical(
                "tamper_detected_config_mac_mismatch",
                expected_mac=expected_mac,
                actual_mac=actual_mac,
            )
            raise ConfigIntegrityError(
                "Agent configuration MAC validation failed: configuration has been tampered with"
            )
        return True

    def assert_integrity_before_stream(self) -> None:
        """Safe failure mode: refuses to stream if tamper was ever detected."""
        if self.is_tampered:
            log.critical("stream_refused_due_to_tamper_flag")
            raise ConfigIntegrityError(
                "Security policy violation: stream refused because agent configuration tamper was detected"
            )


config_integrity_manager = ConfigIntegrityManager()
