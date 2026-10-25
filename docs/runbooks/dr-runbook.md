# NVRSMS Platform — Disaster Recovery & Business Continuity Runbook

## 1. Objectives & Metrics

- **Recovery Point Objective (RPO):** < 1 hour (nightly full encrypted backup + WAL archiving hourly)
- **Recovery Time Objective (RTO):** < 15 minutes (automated decryption, scratch verification, and container spin-up)

---

## 2. Disaster Scenarios & Playbooks

### Scenario A: Hub Database Corruption or Host Loss

#### Step 1: Declare Incident & Isolate Target
1. Notify operations and freeze inbound writes (set Caddy to 503 maintenance page).
2. Stop the application backend:
   ```bash
   docker compose stop hub-backend
   ```

#### Step 2: Retrieve Latest Encrypted Backup
1. Backups are stored encrypted locally at `/var/backups/nvrsms` and copied to off-site object storage (`s3://nvrsms-backups-dr/`).
2. Identify the latest valid backup:
   ```bash
   ls -lat /var/backups/nvrsms/*.meta.json | head -n 1
   ```

#### Step 3: Execute Restoration
1. Run the restore script against the recovery database:
   ```bash
   ./infra/backup/restore.sh <backup_id> postgresql://nvrsms:nvrsms@db:5432/nvrsms
   ```
2. The script will:
   - Validate the SHA-256 checksum of the encrypted archive.
   - Decrypt the payload using the offline disaster recovery key.
   - Verify the unencrypted dump checksum.
   - Reconstruct database schema and tables.

#### Step 4: Verification & Service Resumption
1. Run automated consistency verification:
   ```bash
   python3 -m pytest tests/test_backup_restore.py
   ```
2. Restart hub backend:
   ```bash
   docker compose up -d hub-backend
   ```
3. Verify health endpoint returns HTTP 200:
   ```bash
   curl -i http://localhost:8000/health
   ```

---

### Scenario B: Edge Agent Hardware Replacement / Factory Reset

When an Edge Agent server suffers hardware failure and is replaced:

1. **Deploy New Edge Appliance:** Install fresh OS and Python runtime on new edge hardware.
2. **Retrieve Enrolment Token:**
   - Log into Hub Admin UI (or invoke `POST /api/v1/agents/enrol-token`).
   - Generate a single-use 15-minute enrolment code.
3. **Bootstrap New Agent:**
   ```bash
   python3 -m agent.main --enrol <ENROL_CODE> --hub-url https://hub.nvrsms.local
   ```
4. **Automatic Reconnection & Reconciliation:**
   - The new agent establishes outbound WSS connection `/ws/agent`.
   - Edge Agent loads existing NVR configurations assigned to its location from the Hub.
   - Hub and Edge Agent execute state reconciliation (`reconcile_state`).
   - Active CCTV streaming sessions resume automatically on demand.
