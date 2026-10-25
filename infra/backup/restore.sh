#!/usr/bin/env bash
# NVRSMS Database Disaster Recovery Restore Script
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <backup_id> [target_db_url]"
    exit 1
fi

BACKUP_ID="$1"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/nvrsms}"
TARGET_DB_URL="${2:-${DATABASE_URL:-postgresql://nvrsms:nvrsms@db:5432/nvrsms}}"

echo "Initiating restore of backup '${BACKUP_ID}' into ${TARGET_DB_URL}..."
python3 -c "
from infra.backup.restore import restore_engine
res = restore_engine.restore_database('${BACKUP_DIR}', '${BACKUP_ID}', '${TARGET_DB_URL}')
print('Restore successful:', res)
"
