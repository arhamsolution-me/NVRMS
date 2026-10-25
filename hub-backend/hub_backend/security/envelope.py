"""Envelope encryption (KEK/DEK) with zero-downtime key rotation for stored secrets."""

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
    """Implements two-tier envelope encryption: Primary/fallback KEKs wrap unique per-secret DEKs."""

    def __init__(self, master_key: bytes | None = None) -> None:
        self._keks: list[Fernet] = []
        if master_key:
            self._keks.append(Fernet(master_key))
        else:
            settings = get_settings()
            key_raw = getattr(settings, "encryption_master_key", None)
            if not key_raw:
                derived = hashlib.sha256(b"nvrsms_default_master_kek_key_material").digest()
                key_raw = base64.urlsafe_b64encode(derived)
            elif isinstance(key_raw, str):
                key_raw = key_raw.encode()
            self._keks.append(Fernet(key_raw))

    def add_fallback_kek(self, fallback_key: bytes) -> None:
        """Add a previous KEK to allow zero-downtime decrypt during key rotation."""
        self._keks.append(Fernet(fallback_key))

    def rotate_master_kek(self, new_master_key: bytes) -> None:
        """Promote a new KEK as primary while retaining existing KEKs for zero-downtime decryption."""
        new_fernet = Fernet(new_master_key)
        self._keks.insert(0, new_fernet)

    def encrypt(self, plaintext: str | bytes) -> str:
        """Encrypt secret using a fresh DEK, then wrap the DEK with the primary KEK."""
        raw_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext

        # Generate fresh DEK
        dek = Fernet.generate_key()
        dek_fernet = Fernet(dek)

        # Encrypt plaintext with DEK
        ciphertext = dek_fernet.encrypt(raw_bytes)

        # Wrap DEK with primary KEK
        encrypted_dek = self._keks[0].encrypt(dek)

        envelope = {
            "version": 1,
            "encrypted_dek": base64.b64encode(encrypted_dek).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        return json.dumps(envelope)

    def _unwrap_dek(self, encrypted_dek_bytes: bytes) -> bytes:
        """Attempt to unwrap DEK across primary and fallback KEKs."""
        last_error: Exception | None = None
        for kek in self._keks:
            try:
                return kek.decrypt(encrypted_dek_bytes)
            except InvalidToken as err:
                last_error = err
                continue
        raise EnvelopeEncryptionError(
            f"Failed to unwrap DEK with any configured KEK: {last_error}"
        )

    def decrypt(self, envelope_json: str) -> str:
        """Unwrap DEK using primary or fallback KEK and decrypt ciphertext."""
        try:
            envelope: dict[str, Any] = json.loads(envelope_json)
            if envelope.get("version") != 1:
                raise EnvelopeEncryptionError(
                    f"Unsupported envelope version: {envelope.get('version')}"
                )

            encrypted_dek = base64.b64decode(envelope["encrypted_dek"])
            ciphertext = base64.b64decode(envelope["ciphertext"])

            # Unwrap DEK with primary or fallback KEK
            dek = self._unwrap_dek(encrypted_dek)
            dek_fernet = Fernet(dek)

            # Decrypt payload with DEK
            decrypted_bytes = dek_fernet.decrypt(ciphertext)
            return decrypted_bytes.decode("utf-8")

        except (EnvelopeEncryptionError, InvalidToken, KeyError, ValueError) as exc:
            raise EnvelopeEncryptionError(f"Envelope decryption failed: {exc}") from exc

    def rewrap_dek(self, envelope_json: str) -> str:
        """Rewrap an envelope's DEK with the current primary KEK without decrypting data payload."""
        envelope: dict[str, Any] = json.loads(envelope_json)
        encrypted_dek = base64.b64decode(envelope["encrypted_dek"])

        dek = self._unwrap_dek(encrypted_dek)
        # Wrap with primary KEK
        new_encrypted_dek = self._keks[0].encrypt(dek)

        envelope["encrypted_dek"] = base64.b64encode(new_encrypted_dek).decode("ascii")
        return json.dumps(envelope)


envelope_encryptor = EnvelopeEncryptor()
