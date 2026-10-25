"""Database backup engine with client-side encryption and retention pruning."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

DEFAULT_BACKUP_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(b"nvrsms_default_backup_dr_key").digest()
)


class BackupError(Exception):
    """Raised when backup generation or encryption fails."""


class BackupEngine:
    """Creates encrypted database dumps with cryptographic checksums."""

    def __init__(self, encryption_key: bytes = DEFAULT_BACKUP_KEY) -> None:
        self.fernet = Fernet(encryption_key)

    def create_sqlite_dump(self, db_path: Path | str, output_path: Path | str) -> None:
        """Create a consistent SQLite dump using sqlite3 backup API."""
        path_str = str(db_path)
        is_uri = path_str.startswith("file:") or "uri=true" in path_str.lower()
        src_conn = sqlite3.connect(path_str, uri=is_uri)
        dst_conn = sqlite3.connect(str(output_path))
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()

    def backup_database(
        self,
        db_path_or_url: str,
        dest_dir: Path | str,
        backup_id: str | None = None,
    ) -> dict[str, Any]:
        """Perform full database backup, encrypt it, and write metadata."""
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC)
        bid = backup_id or f"backup_{now.strftime('%Y%m%d_%H%M%S')}"
        raw_dump_path = dest / f"{bid}.dump"
        encrypted_path = dest / f"{bid}.enc"
        meta_path = dest / f"{bid}.meta.json"

        # 1. Dump database
        if db_path_or_url.startswith("postgresql"):
            # PostgreSQL dump
            cmd = ["pg_dump", "-Fc", db_path_or_url, "-f", str(raw_dump_path)]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except Exception as exc:
                raise BackupError(f"pg_dump failed: {exc}") from exc
        else:
            # SQLite dump
            clean_path = db_path_or_url.replace("sqlite+aiosqlite:///", "").replace(
                "sqlite:///", ""
            )
            is_uri = clean_path.startswith("file:") or "uri=true" in clean_path.lower()
            if not is_uri and not os.path.exists(clean_path):
                # New SQLite: create clean snapshot
                conn = sqlite3.connect(clean_path)
                conn.execute("CREATE TABLE IF NOT EXISTS _nvrsms_dr_check (id INTEGER PRIMARY KEY)")
                conn.commit()
                conn.close()
            self.create_sqlite_dump(clean_path, raw_dump_path)

        # 2. Read raw dump and compute checksum
        raw_data = raw_dump_path.read_bytes()
        raw_sha256 = hashlib.sha256(raw_data).hexdigest()

        # 3. Encrypt dump using Fernet (AES-128-CBC + HMAC-SHA256 authenticated encryption)
        encrypted_data = self.fernet.encrypt(raw_data)
        encrypted_path.write_bytes(encrypted_data)
        enc_sha256 = hashlib.sha256(encrypted_data).hexdigest()

        # Clean up unencrypted dump
        if raw_dump_path.exists():
            os.remove(raw_dump_path)

        # 4. Save metadata
        metadata = {
            "backup_id": bid,
            "created_at": now.isoformat(),
            "raw_sha256": raw_sha256,
            "encrypted_sha256": enc_sha256,
            "raw_size_bytes": len(raw_data),
            "encrypted_size_bytes": len(encrypted_data),
            "encrypted_file": encrypted_path.name,
        }
        meta_path.write_text(json.dumps(metadata, indent=2))

        return metadata

    def prune_backups(self, dest_dir: Path | str, max_backups: int = 7) -> list[str]:
        """Prune oldest backups retaining at most max_backups."""
        dest = Path(dest_dir)
        if not dest.exists():
            return []

        meta_files = sorted(
            dest.glob("*.meta.json"),
            key=lambda p: p.stat().st_mtime,
        )

        deleted: list[str] = []
        if len(meta_files) > max_backups:
            to_delete = meta_files[: len(meta_files) - max_backups]
            for m in to_delete:
                base_name = m.name.replace(".meta.json", "")
                enc_file = dest / f"{base_name}.enc"
                if enc_file.exists():
                    os.remove(enc_file)
                os.remove(m)
                deleted.append(base_name)

        return deleted


backup_engine = BackupEngine()
