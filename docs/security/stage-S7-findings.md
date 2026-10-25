# Stage S7: Data Protection and Infrastructure Findings

## 1. Executive Summary

Stage S7 verified data protection at rest, zero-downtime key rotation, backup encryption with restore verification, and immutable cryptographic audit logging across the NVRSMS platform.
The findings and verification evidence confirm:
1. **Zero Plaintext Secrets at Rest**: Database inspection demonstrated that passwords are exclusively stored as Argon2id hashes, agent tokens/codes as SHA-256 digests, and NVR credentials never touch the central Hub database (held only within encrypted machine-scoped agent storage).
2. **Zero-Downtime Envelope Key Rotation**: Master KEK rotation supports multi-key fallback. Stored secrets encrypted under prior KEKs remain decryptable without service interruption, and DEKs can be re-wrapped to new KEKs without decrypting data payloads.
3. **Encrypted Backup & Restore Verification**: Backups are encrypted client-side using authenticated symmetric encryption before leaving the host. Restored SQLite databases pass raw checksum matching and `PRAGMA integrity_check`.
4. **Audit Immutability & Hash Chaining**: Every audit entry is cryptographically bound to the previous entry via a SHA-256 hash chain (`prev_hash`). Tampering with a single historical row or entry attribute breaks the chain and is detected instantly.

---

## 2. Findings and Remediation

### Finding S7-1: Database Credential Exposure Risk (Verified Defended)
- **Vulnerability**: If an insider or attacker obtains a database backup or dump, plaintext credentials or API keys could lead to lateral movement.
- **Verification**: Evaluated raw database dump and entities (`User`, `Agent`, `AgentEnrolmentToken`, `RefreshToken`, `NVR`, `Camera`).
  - Passwords: Argon2id hashes with `$argon2id$v=19$m=65536,t=2,p=1$` parameters.
  - Agent tokens: SHA-256 hashes (`agt_` tokens hashed with `hash_token`).
  - Enrolment codes: SHA-256 hashes.
  - Refresh tokens: SHA-256 hashes.
  - NVR credentials: Hub holds zero NVR passwords. They are held exclusively on the agent inside encrypted local storage.
- **Evidence**: `test_database_dump_contains_zero_plaintext_secrets` passed.

### Finding S7-2: Key Rotation Downtime and Interruption Risk (Fixed)
- **Vulnerability**: Rotating a master encryption key (KEK) could render existing stored envelopes temporarily unreadable or drop active streams while batches re-encrypt.
- **Remediation**: Upgraded `EnvelopeEncryptor` with multi-key KEK fallback and atomic `rotate_master_kek()` and `rewrap_dek()`.
  - New secrets are encrypted under the newly promoted primary KEK.
  - Old secrets are transparently unwrapped using fallback KEKs.
  - Background DEK re-wrapping updates the envelope's encrypted DEK to the new primary KEK without decrypting or re-encrypting the underlying data payload.
- **Evidence**: `test_zero_downtime_envelope_kek_rotation` passed.

### Finding S7-3: Backup Encryption and Tamper Proofing (Verified)
- **Vulnerability**: Unencrypted database backups exported to external storage or cloud buckets could be intercepted.
- **Remediation**: `BackupEngine.backup_database` produces client-side authenticated encrypted dumps (`.enc`) and SHA-256 metadata (`.meta.json`). Raw unencrypted SQLite dumps are scrubbed from disk immediately after encryption. `RestoreEngine` validates both encrypted and raw SHA-256 checksums before applying restore, executing `PRAGMA integrity_check` on the target database.
- **Evidence**: `test_encrypted_backup_creation_and_restore_verification` passed.

### Finding S7-4: Audit Trail Tampering and Non-Repudiation (Fixed)
- **Vulnerability**: An attacker gaining write access to the database could delete or modify audit log records to conceal malicious activity.
- **Remediation**: Added `prev_hash` and `record_hash` columns (migration `0005_audit_hash_chain.py`) to `AuditLog`.
  - Every log entry computes `record_hash = SHA256(prev_hash + action + resource_type + resource_id + user_id + tenant_id + details)`.
  - Strictly monotonic timestamps prevent race conditions in tight loops.
  - Automated verifier `verify_audit_log_chain(db)` iterates the chain. Modifying any historical record attribute immediately flags `Tampered record content` or `Broken hash chain`.
- **Evidence**: `test_audit_log_hash_chain_tamper_detection` passed.

---

## 3. Test Evidence Summary

| Test Case | Objective | Result |
|---|---|---|
| `test_database_dump_contains_zero_plaintext_secrets` | Verify 0 plaintext secrets in raw DB records | PASSED |
| `test_zero_downtime_envelope_kek_rotation` | Verify multi-KEK fallback and non-disruptive rotation | PASSED |
| `test_encrypted_backup_creation_and_restore_verification` | Client-side encrypted backup, restore & PRAGMA check | PASSED |
| `test_audit_log_hash_chain_tamper_detection` | Merkle hash chain validation and tamper detection | PASSED |
| `test_migrations_apply_and_rollback` | Migration 0005 applies and rolls back cleanly | PASSED |

**Total Suite**: 4/4 Stage S7 tests passed. Full platform backend suite: 121/121 passed. Full agent suite: 69/69 passed.
