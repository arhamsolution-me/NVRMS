"""Agent self-updater with cryptographic verification and automatic rollback."""

from __future__ import annotations

import hashlib
import hmac
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.logging_config import get_logger

log = get_logger(__name__)

# Default update signing key (can be overridden via environment or config)
DEFAULT_UPDATE_SECRET = b"nvrsms_firmware_update_hmac_secret_2026"


class UpdateVerificationError(Exception):
    """Raised when update integrity or signature verification fails."""


class AgentUpdater:
    """Safely applies self-updates with rollback on failure."""

    def __init__(self, secret_key: bytes = DEFAULT_UPDATE_SECRET) -> None:
        self.secret_key = secret_key

    def compute_sha256(self, file_path: Path | str) -> str:
        """Compute hex SHA-256 checksum of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def compute_signature(self, file_path: Path | str) -> str:
        """Compute HMAC-SHA256 signature for an update file."""
        signer = hmac.new(self.secret_key, digestmod=hashlib.sha256)
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                signer.update(chunk)
        return signer.hexdigest()

    def verify_package(
        self,
        package_path: Path | str,
        expected_sha256: str,
        signature: str,
    ) -> bool:
        """Verify checksum and cryptographic signature of update package."""
        p = Path(package_path)
        if not p.exists():
            raise UpdateVerificationError(f"Update package not found: {p}")

        # Verify SHA-256
        actual_sha = self.compute_sha256(p)
        if not hmac.compare_digest(actual_sha.lower(), expected_sha256.lower()):
            raise UpdateVerificationError(
                f"Checksum mismatch: expected {expected_sha256}, got {actual_sha}"
            )

        # Verify Signature
        expected_sig = self.compute_signature(p)
        if not hmac.compare_digest(signature.lower(), expected_sig.lower()):
            raise UpdateVerificationError("Cryptographic signature validation failed")

        return True

    def apply_update(
        self,
        current_file: Path | str,
        new_package: Path | str,
        expected_sha256: str,
        signature: str,
        health_check_fn: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Atomically apply update with verification and automatic rollback.

        Args:
            current_file: Path to currently running component file.
            new_package: Path to new verified package.
            expected_sha256: Expected SHA-256 checksum.
            signature: Signature verifying authenticity.
            health_check_fn: Optional callable validating boot/health of new version.

        Returns:
            Dict containing update status and details.
        """
        curr_path = Path(current_file)
        new_path = Path(new_package)
        backup_path = curr_path.with_suffix(curr_path.suffix + ".backup")

        # 1. Verify integrity and signature
        self.verify_package(new_path, expected_sha256, signature)

        # 2. Create backup of current file
        if curr_path.exists():
            shutil.copy2(curr_path, backup_path)
            log.info("created_pre_update_backup", backup_path=str(backup_path))

        try:
            # 3. Apply update (copy new file over current)
            shutil.copy2(new_path, curr_path)
            log.info("applied_new_version", target=str(curr_path))

            # 4. Perform post-update health check
            if health_check_fn is not None:
                is_healthy = health_check_fn()
                if not is_healthy:
                    raise RuntimeError("Post-update health check failed")

            log.info("update_completed_successfully", path=str(curr_path))
            return {
                "status": "success",
                "version_sha": expected_sha256,
                "rolled_back": False,
            }

        except Exception as exc:
            log.error("update_failed_triggering_rollback", error=str(exc))
            # 5. Automatic rollback to backup
            if backup_path.exists():
                shutil.copy2(backup_path, curr_path)
                log.warning("rollback_completed", restored=str(curr_path))
            return {
                "status": "rolled_back",
                "error": str(exc),
                "rolled_back": True,
            }


agent_updater = AgentUpdater()
