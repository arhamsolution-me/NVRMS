# CCTV Hub & Agent Platform — Stage 7 Plan

## Stage: Backup and Disaster Recovery

### Objective
Implement end-to-end automated database and configuration backup, encryption, retention pruning, and zero-data-loss disaster recovery verification:
1. **Automated Encrypted Backup Suite (`infra/backup/`)**:
   - `backup.py` / `backup.sh`:
     - Creates PostgreSQL dump / SQLite snapshot with WAL archiving metadata.
     - Encrypts backup archive using AES-256-CBC / Fernet with HMAC integrity verification.
     - Prunes backups according to retention policy (7 daily, 4 weekly, 12 monthly).
   - `restore.py` / `restore.sh`:
     - Decrypts and verifies HMAC checksum of backup archives.
     - Reconstructs database into target database (or scratch verification database).
     - Reconciles sequence numbers and table records.
2. **Automated Scratch Verification Engine (`hub_backend/services/dr_verify.py`)**:
   - Daily automated restore verification job:
     - Backs up current database.
     - Restores into an isolated scratch database.
     - Runs record count and checksum verification against source tables (`users`, `tenants`, `roles`, `nvrs`, `cameras`).
     - Emits alert event if backup integrity check or scratch restore fails.
3. **Agent Re-enrolment & Config Recovery**:
   - Agent config backup export and restore procedure when edge hardware is replaced or wiped.
4. **Disaster Recovery Runbook (`docs/runbooks/dr-runbook.md`)**:
   - Defined RTO (Recovery Time Objective < 15 minutes) and RPO (Recovery Point Objective < 1 hour).
   - Step-by-step failover and restore runbook.

---

### Files to Create / Modify

#### Infrastructure & Scripts (`infra/backup/`)
- `infra/backup/backup.py` — Encrypted database backup, checksumming, and retention pruning engine
- `infra/backup/restore.py` — Decryption, integrity check, and database restoration tool
- `infra/backup/backup.sh` — Wrapper shell script for cron/orchestration
- `infra/backup/restore.sh` — Wrapper shell script for DR recovery

#### Hub Backend
- `hub_backend/services/dr_verify.py` — Automated backup and scratch restore integrity verifier
- `hub_backend/routes/dr.py` — REST endpoints for triggering on-demand backup and inspecting DR status

#### Documentation
- `docs/runbooks/dr-runbook.md` — Formal disaster recovery runbook with RTO, RPO, and execution steps

#### Tests
- Backup & DR Tests (`hub-backend/tests/test_backup_restore.py`):
  - Backup file creation, AES-256 encryption, and HMAC generation
  - Restore from valid encrypted backup with 100% data fidelity
  - Corrupted backup archive detection (tampered ciphertext or bad HMAC rejected)
  - Retention pruning (retaining correct count of daily/weekly/monthly backups)
  - Point-in-time recovery & scratch restore verification check

---

### Exit Gate Criteria
- [ ] Automated backup creates encrypted archive with cryptographic checksum
- [ ] Full restore proven by automated test with record count and checksum match
- [ ] Corrupted or tampered backup archive is detected and rejected
- [ ] Retention policy prunes expired backups cleanly
- [ ] DR runbook (`docs/runbooks/dr-runbook.md`) complete with RTO and RPO
- [ ] 100% of tests pass with zero regressions
