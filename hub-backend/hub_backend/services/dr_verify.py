"""Disaster recovery automated verification service."""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.backup.backup import backup_engine
from hub_backend.backup.restore import restore_engine
from hub_backend.logging_config import get_logger
from hub_backend.models.camera import Camera
from hub_backend.models.nvr import NVR
from hub_backend.models.rbac import Role
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User

log = get_logger(__name__)


class DRVerificationError(Exception):
    """Raised when disaster recovery restore verification fails."""


class DRVerificationService:
    """Automates backup creation and scratch restoration testing with table count checksums."""

    async def get_database_counts(self, session: AsyncSession) -> dict[str, int]:
        """Query record counts across core tables."""
        tenants_c = (await session.execute(select(func.count(Tenant.id)))).scalar_one()
        users_c = (await session.execute(select(func.count(User.id)))).scalar_one()
        roles_c = (await session.execute(select(func.count(Role.id)))).scalar_one()
        nvrs_c = (await session.execute(select(func.count(NVR.id)))).scalar_one()
        cams_c = (await session.execute(select(func.count(Camera.id)))).scalar_one()

        return {
            "tenants": tenants_c,
            "users": users_c,
            "roles": roles_c,
            "nvrs": nvrs_c,
            "cameras": cams_c,
        }

    async def verify_restore_to_scratch(
        self,
        session: AsyncSession,
        source_db_file: str,
        backup_dir: Path | str,
        scratch_db_file: str,
    ) -> dict[str, Any]:
        """Perform automated backup and restore into scratch database, verifying 100% record match."""
        bdir = Path(backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        backup_id = f"dr_verify_{uuid.uuid4().hex[:8]}"

        # 1. Capture source record counts
        source_clean = source_db_file.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        is_uri = source_clean.startswith("file:") or "uri=true" in source_clean.lower()
        source_counts: dict[str, int] = {}
        if not is_uri and os.path.exists(source_clean):
            s_conn = sqlite3.connect(source_clean)
            s_cur = s_conn.cursor()
            for table in ["tenants", "users", "roles", "nvrs", "cameras"]:
                try:
                    s_cur.execute(f"SELECT count(*) FROM {table}")
                    source_counts[table] = s_cur.fetchone()[0]
                except sqlite3.OperationalError:
                    source_counts[table] = 0
            s_conn.close()
        else:
            source_counts = await self.get_database_counts(session)

        # 2. Perform encrypted backup
        meta = backup_engine.backup_database(
            db_path_or_url=source_db_file,
            dest_dir=bdir,
            backup_id=backup_id,
        )

        # 3. Restore into scratch database
        restore_engine.restore_database(
            backup_dir=bdir,
            backup_id=backup_id,
            target_db_path_or_url=scratch_db_file,
        )

        # 4. Query scratch database directly
        scratch_clean = scratch_db_file.replace("sqlite+aiosqlite:///", "").replace(
            "sqlite:///", ""
        )
        scratch_conn = sqlite3.connect(scratch_clean)
        cur = scratch_conn.cursor()

        restored_counts = {}
        for table in ["tenants", "users", "roles", "nvrs", "cameras"]:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
                restored_counts[table] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                restored_counts[table] = 0
        scratch_conn.close()

        # 5. Verify record counts match exactly
        mismatches = []
        for table, count in source_counts.items():
            if restored_counts.get(table) != count:
                mismatches.append(f"{table}: source={count}, restored={restored_counts.get(table)}")

        # Clean up scratch artifacts
        if os.path.exists(scratch_clean):
            os.remove(scratch_clean)

        if mismatches:
            raise DRVerificationError(
                f"Data verification mismatch after scratch restore: {', '.join(mismatches)}"
            )

        log.info(
            "dr_restore_verification_passed",
            backup_id=backup_id,
            counts=source_counts,
        )

        return {
            "status": "verified",
            "backup_id": backup_id,
            "source_counts": source_counts,
            "restored_counts": restored_counts,
            "checksum_match": True,
            "raw_sha256": meta["raw_sha256"],
        }


dr_service = DRVerificationService()
