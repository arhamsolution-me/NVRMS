"""Tests for database backup, encryption, retention pruning, and DR scratch verification."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.backup import (
    BackupEngine,
    RestoreEngine,
    RestoreError,
    backup_engine,
    restore_engine,
)
from hub_backend.services.dr_verify import dr_service


@pytest.fixture
def sample_sqlite_db(tmp_path: Path) -> Path:
    """Create a sample SQLite database populated with test records."""
    db_file = tmp_path / "source.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY, name TEXT);")
    cur.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT);")
    cur.execute("CREATE TABLE roles (id TEXT PRIMARY KEY, name TEXT);")
    cur.execute("CREATE TABLE nvrs (id TEXT PRIMARY KEY, name TEXT);")
    cur.execute("CREATE TABLE cameras (id TEXT PRIMARY KEY, name TEXT);")

    cur.execute("INSERT INTO tenants VALUES ('t1', 'Acme Corp');")
    cur.execute("INSERT INTO users VALUES ('u1', 'alice@acme.com');")
    cur.execute("INSERT INTO roles VALUES ('r1', 'Admin');")
    cur.execute("INSERT INTO nvrs VALUES ('n1', 'Office NVR');")
    cur.execute("INSERT INTO cameras VALUES ('c1', 'Lobby Camera');")
    conn.commit()
    conn.close()
    return db_file


class TestBackupAndRestoreEngine:
    """Tests for core backup creation, encryption, and restoration fidelity."""

    def test_backup_encrypts_and_creates_metadata(
        self, tmp_path: Path, sample_sqlite_db: Path
    ) -> None:
        backup_dir = tmp_path / "backups"
        meta = backup_engine.backup_database(
            db_path_or_url=str(sample_sqlite_db),
            dest_dir=backup_dir,
            backup_id="test_bk_01",
        )

        assert meta["backup_id"] == "test_bk_01"
        assert meta["encrypted_file"] == "test_bk_01.enc"
        assert meta["raw_size_bytes"] > 0
        assert meta["encrypted_size_bytes"] > 0

        # Unencrypted dump must have been cleaned up
        assert not (backup_dir / "test_bk_01.dump").exists()
        # Encrypted file and metadata must exist
        assert (backup_dir / "test_bk_01.enc").exists()
        assert (backup_dir / "test_bk_01.meta.json").exists()

    def test_restore_valid_archive_succeeds(self, tmp_path: Path, sample_sqlite_db: Path) -> None:
        backup_dir = tmp_path / "backups"
        backup_engine.backup_database(
            db_path_or_url=str(sample_sqlite_db),
            dest_dir=backup_dir,
            backup_id="test_bk_restore",
        )

        restored_db = tmp_path / "restored.db"
        res = restore_engine.restore_database(
            backup_dir=backup_dir,
            backup_id="test_bk_restore",
            target_db_path_or_url=str(restored_db),
        )

        assert res["status"] == "success"
        assert res["checksum_verified"] is True
        assert restored_db.exists()

        # Verify restored data
        conn = sqlite3.connect(str(restored_db))
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM tenants")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM cameras")
        assert cur.fetchone()[0] == 1
        conn.close()

    def test_tampered_encrypted_archive_rejected(
        self, tmp_path: Path, sample_sqlite_db: Path
    ) -> None:
        backup_dir = tmp_path / "backups"
        backup_engine.backup_database(
            db_path_or_url=str(sample_sqlite_db),
            dest_dir=backup_dir,
            backup_id="test_bk_tamper",
        )

        enc_file = backup_dir / "test_bk_tamper.enc"
        # Flip bits in encrypted file
        data = bytearray(enc_file.read_bytes())
        data[20] = (data[20] + 1) % 256
        enc_file.write_bytes(data)

        restored_db = tmp_path / "tampered.db"
        with pytest.raises(RestoreError, match="tampered"):
            restore_engine.restore_database(
                backup_dir=backup_dir,
                backup_id="test_bk_tamper",
                target_db_path_or_url=str(restored_db),
            )

    def test_wrong_encryption_key_rejected(self, tmp_path: Path, sample_sqlite_db: Path) -> None:
        key_a = Fernet.generate_key()
        key_b = Fernet.generate_key()

        engine_a = BackupEngine(encryption_key=key_a)
        engine_b = RestoreEngine(encryption_key=key_b)

        backup_dir = tmp_path / "backups"
        engine_a.backup_database(
            db_path_or_url=str(sample_sqlite_db),
            dest_dir=backup_dir,
            backup_id="test_key_mismatch",
        )

        restored_db = tmp_path / "mismatch.db"
        with pytest.raises(RestoreError, match="decryption failed"):
            engine_b.restore_database(
                backup_dir=backup_dir,
                backup_id="test_key_mismatch",
                target_db_path_or_url=str(restored_db),
            )

    def test_retention_pruning_retains_limit(self, tmp_path: Path, sample_sqlite_db: Path) -> None:
        backup_dir = tmp_path / "backups_prune"
        for i in range(6):
            backup_engine.backup_database(
                db_path_or_url=str(sample_sqlite_db),
                dest_dir=backup_dir,
                backup_id=f"prune_test_{i}",
            )

        # Retain at most 2 backups
        deleted = backup_engine.prune_backups(backup_dir, max_backups=2)
        assert len(deleted) == 4

        remaining = list(backup_dir.glob("*.meta.json"))
        assert len(remaining) == 2


class TestDRRestoreVerificationService:
    """Tests for automated scratch database restoration and record verification."""

    @pytest.mark.asyncio
    async def test_scratch_restore_verification_flow(
        self, tmp_path: Path, sample_sqlite_db: Path, db_session: AsyncSession
    ) -> None:
        backup_dir = tmp_path / "dr_verify_backups"
        scratch_db = tmp_path / "scratch_target.db"

        res = await dr_service.verify_restore_to_scratch(
            session=db_session,
            source_db_file=str(sample_sqlite_db),
            backup_dir=backup_dir,
            scratch_db_file=str(scratch_db),
        )

        assert res["status"] == "verified"
        assert res["checksum_match"] is True
        assert res["source_counts"]["tenants"] >= 1
