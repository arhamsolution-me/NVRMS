"""Disk usage monitor and bounded FIFO log cleanup."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from agent.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_MIN_FREE_MB = 500.0
DEFAULT_MAX_USED_PERCENT = 90.0
DEFAULT_MAX_LOG_FILES = 5


class DiskMonitor:
    """Monitors disk usage and performs bounded FIFO log rotation/cleanup."""

    def __init__(
        self,
        min_free_mb: float = DEFAULT_MIN_FREE_MB,
        max_used_percent: float = DEFAULT_MAX_USED_PERCENT,
        max_log_files: int = DEFAULT_MAX_LOG_FILES,
    ) -> None:
        self.min_free_mb = min_free_mb
        self.max_used_percent = max_used_percent
        self.max_log_files = max_log_files

    def get_disk_stats(self, target_path: Path | str) -> dict[str, Any]:
        """Query disk capacity and free space."""
        path_obj = Path(target_path)
        if not path_obj.exists():
            path_obj.mkdir(parents=True, exist_ok=True)

        usage = shutil.disk_usage(str(path_obj))
        total_mb = usage.total / (1024 * 1024)
        used_mb = usage.used / (1024 * 1024)
        free_mb = usage.free / (1024 * 1024)
        used_pct = (usage.used / usage.total) * 100.0 if usage.total > 0 else 0.0

        is_critical = free_mb < self.min_free_mb or used_pct > self.max_used_percent

        return {
            "total_mb": round(total_mb, 2),
            "used_mb": round(used_mb, 2),
            "free_mb": round(free_mb, 2),
            "used_percent": round(used_pct, 2),
            "is_critical": is_critical,
        }

    def prune_old_logs(
        self,
        log_dir: Path | str,
        max_files: int | None = None,
        force: bool = False,
    ) -> list[str]:
        """Prune oldest log files if disk is critical or file count exceeds limit.

        Returns:
            List of deleted file paths.
        """
        dir_path = Path(log_dir)
        if not dir_path.exists() or not dir_path.is_dir():
            return []

        limit = max_files if max_files is not None else self.max_log_files
        stats = self.get_disk_stats(dir_path)

        # Collect log files sorted by modification time (oldest first)
        log_files: list[Path] = sorted(
            [p for p in dir_path.glob("*.log*") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
        )

        deleted: list[str] = []

        # If file count exceeds max limit or disk is critical or forced:
        should_prune = force or stats["is_critical"] or len(log_files) > limit

        if should_prune:
            # We want to keep at most limit files, or prune down until under limit
            num_to_delete = max(len(log_files) - limit, 0)
            if stats["is_critical"] and num_to_delete == 0 and len(log_files) > 1:
                # If still critical, delete at least one oldest file (preserving current active log)
                num_to_delete = 1

            for f in log_files[:num_to_delete]:
                try:
                    f_name = str(f)
                    os.remove(f)
                    deleted.append(f_name)
                    log.warning("pruned_old_log_file", path=f_name)
                except OSError as exc:
                    log.error("failed_to_delete_log", path=str(f), error=str(exc))

        return deleted


disk_monitor = DiskMonitor()
