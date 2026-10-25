#!/usr/bin/env bash
# NVRSMS Automated Backup Script
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/nvrsms}"
DATABASE_URL="${DATABASE_URL:-postgresql://nvrsms:nvrsms@db:5432/nvrsms}"
RETENTION_COUNT="${RETENTION_COUNT:-7}"

echo "Starting NVRSMS database backup to ${BACKUP_DIR}..."
python3 -m infra.backup.backup "${DATABASE_URL}" "${BACKUP_DIR}"

echo "Pruning backups beyond retention limit (${RETENTION_COUNT})..."
python3 -c "from infra.backup.backup import backup_engine; backup_engine.prune_backups('${BACKUP_DIR}', ${RETENTION_COUNT})"

echo "Backup completed successfully."
