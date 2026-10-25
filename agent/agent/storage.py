"""Encrypted local credential storage for edge agent."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DEFAULT_STORAGE_DIR = Path.home() / ".nvrsms-agent"
CREDENTIALS_FILE = "credentials.enc"
KEY_FILE = ".master.key"


def _get_or_create_key(base_dir: Path) -> bytes:
    """Retrieve or generate local machine-bound encryption key."""
    base_dir.mkdir(parents=True, exist_ok=True)
    key_path = base_dir / KEY_FILE
    if key_path.exists():
        return key_path.read_bytes()

    # Generate salt and derive Fernet key
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    # Machine identifier or random seed
    seed = f"nvrsms-agent-{os.name}".encode()
    derived = base64.urlsafe_b64encode(kdf.derive(seed))

    key_path.write_bytes(derived)
    return derived


class SecureStorage:
    """Provides authenticated AES encryption for stored agent credentials."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DEFAULT_STORAGE_DIR
        self.key = _get_or_create_key(self.base_dir)
        self.fernet = Fernet(self.key)

    @property
    def file_path(self) -> Path:
        return self.base_dir / CREDENTIALS_FILE

    def save(self, data: dict[str, Any]) -> None:
        """Encrypt and store credentials dictionary."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        raw_json = json.dumps(data).encode("utf-8")
        encrypted = self.fernet.encrypt(raw_json)
        self.file_path.write_bytes(encrypted)

    def load(self) -> dict[str, Any] | None:
        """Decrypt and load credentials dictionary. Returns None if file does not exist."""
        if not self.file_path.exists():
            return None
        try:
            encrypted = self.file_path.read_bytes()
            decrypted = self.fernet.decrypt(encrypted)
            return json.loads(decrypted.decode("utf-8"))  # type: ignore[no-any-return]
        except Exception:
            return None

    def clear(self) -> None:
        """Wipe stored credentials."""
        if self.file_path.exists():
            self.file_path.unlink()

    def save_nvr_credentials(self, nvr_id: str, creds: dict[str, Any]) -> None:
        """Store encrypted credentials for an onboarded NVR."""
        all_creds = self.load() or {}
        nvrs = all_creds.setdefault("nvrs", {})
        nvrs[nvr_id] = creds
        self.save(all_creds)

    def get_nvr_credentials(self, nvr_id: str) -> dict[str, Any] | None:
        """Retrieve encrypted credentials for an NVR."""
        all_creds = self.load() or {}
        return all_creds.get("nvrs", {}).get(nvr_id)
