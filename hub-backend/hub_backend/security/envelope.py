"""Envelope encryption (KEK/DEK) for stored secrets and credentials."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from hub_backend.config import get_settings


class EnvelopeEncryptionError(Exception):
    """Raised when envelope encryption or decryption fails."""


class EnvelopeEncryptor:
    """Implements two-tier envelope encryption: KEK wraps unique per-secret DEKs."""

    def __init__(self, master_key: bytes | None = None) -> None:
        if master_key:
            self._kek_fernet = Fernet(master_key)
        else:
            settings = get_settings()
            key_raw = getattr(settings, "encryption_master_key", None)
            if not key_raw:
                # Derive a deterministic 32-byte urlsafe Fernet key via SHA-256
                derived = hashlib.sha256(b"nvrsms_default_master_kek_key_material").digest()
                key_raw = base64.urlsafe_b64encode(derived)
            elif isinstance(key_raw, str):
                key_raw = key_raw.encode()
            self._kek_fernet = Fernet(key_raw)

    def encrypt(self, plaintext: str | bytes) -> str:
        """Encrypt secret using a fresh DEK, then wrap the DEK with the master KEK.

        Returns:
            JSON string containing encrypted_dek, ciphertext, and metadata.
        """
        raw_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext

        # Generate fresh DEK
        dek = Fernet.generate_key()
        dek_fernet = Fernet(dek)

        # Encrypt plaintext with DEK
        ciphertext = dek_fernet.encrypt(raw_bytes)

        # Wrap DEK with KEK
        encrypted_dek = self._kek_fernet.encrypt(dek)

        envelope = {
            "version": 1,
            "encrypted_dek": base64.b64encode(encrypted_dek).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        return json.dumps(envelope)

    def decrypt(self, envelope_json: str) -> str:
        """Unwrap DEK using master KEK and decrypt ciphertext."""
        try:
            envelope: dict[str, Any] = json.loads(envelope_json)
            if envelope.get("version") != 1:
                raise EnvelopeEncryptionError(
                    f"Unsupported envelope version: {envelope.get('version')}"
                )

            encrypted_dek = base64.b64decode(envelope["encrypted_dek"])
            ciphertext = base64.b64decode(envelope["ciphertext"])

            # Unwrap DEK with KEK
            dek = self._kek_fernet.decrypt(encrypted_dek)
            dek_fernet = Fernet(dek)

            # Decrypt payload with DEK
            decrypted_bytes = dek_fernet.decrypt(ciphertext)
            return decrypted_bytes.decode("utf-8")

        except (InvalidToken, KeyError, ValueError) as exc:
            raise EnvelopeEncryptionError(f"Envelope decryption failed: {exc}") from exc


envelope_encryptor = EnvelopeEncryptor()
