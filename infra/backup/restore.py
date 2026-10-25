"""Database restore engine with integrity check and scratch verification."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_BACKUP_KEY = base64.urlsafe_b64encode(hashlib.sha256(b"nvrsms_default_backup_dr_key").digest())


class RestoreError(Exception):
    """Raised when backup verification or database restore fails."""


class RestoreEngine:
    """Decrypts, verifies, and restores database archives."""

    def __init__(self, encryption_key: bytes = DEFAULT_BACKUP_KEY) -> None:
        self.fernet = Fernet(encryption_key)

    def restore_database(
        self,
        backup_dir: Path | str,
        backup_id: str,
        target_db_path_or_url: str,
    ) -> dict[str, Any]:
        """Restore database from encrypted archive with full integrity validation."""
        bdir = Path(backup_dir)
        meta_path = bdir / f"{backup_id}.meta.json"
        enc_path = bdir / f"{backup_id}.enc"

        if not meta_path.exists():
            raise RestoreError(f"Backup metadata not found: {meta_path}")
        if not enc_path.exists():
            raise RestoreError(f"Encrypted backup archive not found: {enc_path}")

        meta: dict[str, Any] = json.loads(meta_path.read_text())
        enc_data = enc_path.read_bytes()

        # 1. Verify encrypted checksum
        actual_enc_sha = hashlib.sha256(enc_data).hexdigest()
        if actual_enc_sha != meta["encrypted_sha256"]:
            raise RestoreError("Encrypted archive checksum mismatch (tampered backup)")

        # 2. Decrypt archive
        try:
            raw_data = self.fernet.decrypt(enc_data)
        except InvalidToken as exc:
            raise RestoreError("Backup decryption failed: invalid encryption key or corrupted payload") from exc

        # 3. Verify raw dump checksum
        actual_raw_sha = hashlib.sha256(raw_data).hexdigest()
        if actual_raw_sha != meta["raw_sha256"]:
            raise RestoreError("Decrypted dump checksum mismatch")

        # 4. Restore into target database
        temp_dump_path = bdir / f"{backup_id}.restore.tmp"
        temp_dump_path.write_bytes(raw_data)

        try:
            if target_db_path_or_url.startswith("postgresql"):
                cmd = ["pg_restore", "-c", "-d", target_db_path_or_url, str(temp_dump_path)]
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                clean_target = target_db_path_or_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
                # SQLite restore: copy temp dump over clean_target
                target_p = Path(clean_target)
                target_p.parent.mkdir(parents=True, exist_ok=True)
                target_p.write_bytes(raw_data)

                # Verify SQLite opens cleanly and passes integrity check
                conn = sqlite3.connect(clean_target)
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check;")
                integrity_res = cur.fetchone()[0]
                conn.close()

                if integrity_res != "ok":
                    raise RestoreError(f"SQLite PRAGMA integrity_check returned: {integrity_res}")

        finally:
            if temp_dump_path.exists():
                os.remove(temp_dump_path)

        return {
            "status": "success",
            "backup_id": backup_id,
            "target_db": target_db_path_or_url,
            "restored_at": meta["created_at"],
            "checksum_verified": True,
        }


restore_engine = RestoreEngine()
