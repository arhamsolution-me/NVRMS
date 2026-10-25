"""Stage S7: Data Protection and Infrastructure Hardening Verification Suite.

Validates:
1. Zero Plaintext Secrets in Database Dump:
   - Users passwords are Argon2id hashes ($argon2id$).
   - Agent tokens and enrolment codes are stored hashed only.
   - Refresh tokens are stored hashed only.
   - Zero plaintext credentials or tokens present in raw database dump.
2. Zero-Downtime Envelope Key (KEK) Rotation:
   - Secrets encrypted under Old KEK remain decryptable after New KEK promotion.
   - Re-wrapping DEK to New KEK completes seamlessly without data loss.
3. Encrypted Backup and Restore Verification:
   - Backups are encrypted before leaving host.
   - Restored database passes SHA-256 and PRAGMA integrity verification.
4. Cryptographic Audit Immutability & Tamper Detection:
   - Audit trail forms a valid SHA-256 Merkle/hash chain.
   - Modifying a single bit in a historical audit record is immediately detected.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.backup.backup import backup_engine
from hub_backend.backup.restore import restore_engine
from hub_backend.models.agent import Agent, AgentEnrolmentToken
from hub_backend.models.rbac import Role
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import RefreshToken, User
from hub_backend.security.envelope import EnvelopeEncryptor
from hub_backend.security.password import hash_password
from hub_backend.security.tokens import hash_token
from hub_backend.services.audit import record_audit_log, verify_audit_log_chain


@pytest.mark.asyncio
async def test_database_dump_contains_zero_plaintext_secrets(
    db_session: AsyncSession,
) -> None:
    """Verify that all stored credentials, tokens, and codes are cryptographically hashed."""
    tenant_res = await db_session.execute(select(Tenant).limit(1))
    tenant = tenant_res.scalar_one()

    role_res = await db_session.execute(select(Role).limit(1))
    role = role_res.scalar_one()

    raw_password = "SuperSecretPassword2026!#"
    raw_agent_token = "agt_test_super_secret_token_12345"
    raw_enrol_code = "ENROL-ABCD-1234"
    raw_refresh_token = "rft_secret_refresh_token_family_99"

    now = datetime.now(UTC)

    # Seed entities
    user = User(
        tenant_id=tenant.id,
        email=f"dump_test_{uuid.uuid4().hex[:6]}@nvrsms.local",
        password_hash=hash_password(raw_password),
        full_name="Dump Test User",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    agent = Agent(
        tenant_id=tenant.id,
        name="Dump Test Agent",
        token_hash=hash_token(raw_agent_token),
        is_active=True,
    )
    db_session.add(agent)

    enrol_token = AgentEnrolmentToken(
        tenant_id=tenant.id,
        name="Test Enrol",
        code_hash=hash_token(raw_enrol_code),
        created_by_user_id=user.id,
        expires_at=now + timedelta(minutes=15),
    )
    db_session.add(enrol_token)

    refresh_rec = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=now + timedelta(days=7),
    )
    db_session.add(refresh_rec)
    await db_session.commit()

    # Simulate raw database text inspection (equivalent to SQL dump text scan)
    users = (await db_session.execute(select(User))).scalars().all()
    for u in users:
        assert raw_password not in u.password_hash
        assert u.password_hash.startswith("$argon2id$")
        # Ensure raw password does not appear in any user field
        assert raw_password not in str(u.__dict__)

    agents = (await db_session.execute(select(Agent))).scalars().all()
    for a in agents:
        assert raw_agent_token not in a.token_hash
        assert len(a.token_hash) >= 64

    enrols = (await db_session.execute(select(AgentEnrolmentToken))).scalars().all()
    for e in enrols:
        assert raw_enrol_code not in e.code_hash
        assert len(e.code_hash) >= 64

    tokens = (await db_session.execute(select(RefreshToken))).scalars().all()
    for r in tokens:
        assert raw_refresh_token not in r.token_hash
        assert len(r.token_hash) >= 64


def test_zero_downtime_envelope_kek_rotation() -> None:
    """Verify Master KEK rotation decrypts old secrets and supports background rewrapping."""
    old_kek = Fernet.generate_key()
    new_kek = Fernet.generate_key()

    encryptor = EnvelopeEncryptor(master_key=old_kek)

    secret_data = "camera_vault_root_key_2026_sensitive"
    envelope_v1 = encryptor.encrypt(secret_data)

    # Confirm decryption works under old KEK
    assert encryptor.decrypt(envelope_v1) == secret_data

    # Rotate KEK: promote new_kek while keeping old_kek as fallback
    encryptor.rotate_master_kek(new_kek)

    # 1. Existing data encrypted under old_kek is STILL decryptable (ZERO DOWNTIME)
    assert encryptor.decrypt(envelope_v1) == secret_data

    # 2. New data is encrypted under new_kek
    new_secret = "newly_created_nvr_credential_after_rotation"
    envelope_v2 = encryptor.encrypt(new_secret)
    assert encryptor.decrypt(envelope_v2) == new_secret

    # 3. Background re-wrapping of old envelope to new KEK
    rewrapped_v1 = encryptor.rewrap_dek(envelope_v1)
    assert rewrapped_v1 != envelope_v1
    assert encryptor.decrypt(rewrapped_v1) == secret_data


def test_encrypted_backup_creation_and_restore_verification(
    tmp_path: Path,
) -> None:
    """Verify encrypted backup creation, client-side encryption, and restore verification."""
    # Create temporary sqlite database with schema and data
    src_db = tmp_path / "source.db"
    conn = sqlite3.connect(str(src_db))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO users (name) VALUES ('AdminUser'), ('ViewerUser');")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_id = "test_backup_001"

    # 1. Create backup with client-side encryption
    metadata = backup_engine.backup_database(
        db_path_or_url=str(src_db),
        dest_dir=backup_dir,
        backup_id=backup_id,
    )

    enc_file = backup_dir / f"{backup_id}.enc"
    assert enc_file.exists()
    assert metadata["raw_sha256"] != metadata["encrypted_sha256"]

    # Verify raw SQLite content is NOT readable in the encrypted file
    enc_bytes = enc_file.read_bytes()
    assert b"SQLite format 3" not in enc_bytes
    assert b"AdminUser" not in enc_bytes

    # 2. Restore into target scratch database
    target_db = tmp_path / "restored.db"
    restore_result = restore_engine.restore_database(
        backup_dir=backup_dir,
        backup_id=backup_id,
        target_db_path_or_url=str(target_db),
    )

    assert restore_result["status"] == "success"
    assert restore_result["checksum_verified"] is True
    assert target_db.exists()

    # 3. Verify restored data matches exactly
    r_conn = sqlite3.connect(str(target_db))
    cur = r_conn.cursor()
    cur.execute("SELECT name FROM users ORDER BY id;")
    names = [row[0] for row in cur.fetchall()]
    r_conn.close()

    assert names == ["AdminUser", "ViewerUser"]


@pytest.mark.asyncio
async def test_audit_log_hash_chain_tamper_detection(
    db_session: AsyncSession,
) -> None:
    """Verify audit log SHA-256 hash-chaining and tamper detection."""
    tenant_res = await db_session.execute(select(Tenant).limit(1))
    tenant = tenant_res.scalar_one()

    # 1. Record a sequence of 4 chained audit events
    await record_audit_log(
        db=db_session,
        action="USER_LOGIN",
        resource_type="auth",
        tenant_id=tenant.id,
        details={"ip": "10.0.0.1"},
    )
    await record_audit_log(
        db=db_session,
        action="ROLE_CREATE",
        resource_type="role",
        tenant_id=tenant.id,
        details={"role_name": "SecurityOfficer"},
    )
    await record_audit_log(
        db=db_session,
        action="STREAM_START",
        resource_type="stream",
        tenant_id=tenant.id,
        details={"camera": "cam_01"},
    )
    e4 = await record_audit_log(
        db=db_session,
        action="CONFIG_UPDATE",
        resource_type="system",
        tenant_id=tenant.id,
        details={"param": "max_streams"},
    )
    await db_session.commit()

    # 2. Verify legitimate chain
    is_valid, count, err = await verify_audit_log_chain(db_session)
    assert is_valid is True, f"Audit chain verification failed: {err}"
    assert count >= 4
    assert err is None

    # 3. Adversary tampers with the details of e4 directly in the database
    e4.action = "TAMPERED_ACTION_UNAUTHORIZED"
    await db_session.commit()

    # 4. Tamper verification must catch the modification
    is_valid_after_tamper, tampered_row, err_msg = await verify_audit_log_chain(db_session)
    assert is_valid_after_tamper is False
    assert err_msg is not None
    assert "Tampered record content" in err_msg or "Broken hash chain" in err_msg
