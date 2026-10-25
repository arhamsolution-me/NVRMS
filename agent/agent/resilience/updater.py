"""Agent self-updater with Ed25519 cryptographic verification, version downgrade defense, and automatic rollback."""

from __future__ import annotations

import hashlib
import hmac
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from agent.logging_config import get_logger

log = get_logger(__name__)

# Default update signing key (for backward-compatible tests)
DEFAULT_UPDATE_SECRET = b"nvrsms_firmware_update_hmac_secret_2026"


def parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse semver string into a comparable tuple of integers."""
    parts = re.findall(r"\d+", version_str)
    return tuple(int(p) for p in parts) if parts else (0,)


class UpdateVerificationError(Exception):
    """Raised when update integrity, signature, or downgrade verification fails."""


class AgentUpdater:
    """Safely applies self-updates with Ed25519 verification, downgrade defense, and automatic rollback."""

    def __init__(
        self,
        secret_key: bytes = DEFAULT_UPDATE_SECRET,
        trusted_public_key: ed25519.Ed25519PublicKey | bytes | None = None,
    ) -> None:
        self.secret_key = secret_key
        if isinstance(trusted_public_key, bytes):
            self.trusted_public_key = ed25519.Ed25519PublicKey.from_public_bytes(trusted_public_key)
        else:
            self.trusted_public_key = trusted_public_key

    def compute_sha256(self, file_path: Path | str) -> str:
        """Compute hex SHA-256 checksum of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def compute_signature(self, file_path: Path | str) -> str:
        """Compute HMAC-SHA256 signature for an update file (legacy)."""
        signer = hmac.new(self.secret_key, digestmod=hashlib.sha256)
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                signer.update(chunk)
        return signer.hexdigest()

    def sign_package_ed25519(
        self, file_path: Path | str, private_key: ed25519.Ed25519PrivateKey
    ) -> str:
        """Sign update package with an Ed25519 private key, returning hex signature."""
        data = Path(file_path).read_bytes()
        sig = private_key.sign(data)
        return sig.hex()

    def verify_package(
        self,
        package_path: Path | str,
        expected_sha256: str,
        signature: str,
        target_version: str | None = None,
        current_version: str | None = None,
    ) -> bool:
        """Verify checksum, cryptographic signature (Ed25519 or HMAC), and downgrade protection."""
        p = Path(package_path)
        if not p.exists():
            raise UpdateVerificationError(f"Update package not found: {p}")

        # 1. Version downgrade check
        if target_version and current_version:
            target_t = parse_version_tuple(target_version)
            current_t = parse_version_tuple(current_version)
            if target_t < current_t:
                log.warning(
                    "version_downgrade_rejected",
                    current_version=current_version,
                    target_version=target_version,
                )
                raise UpdateVerificationError(
                    f"Version downgrade rejected: cannot downgrade from {current_version} to {target_version}"
                )

        # 2. Verify SHA-256
        actual_sha = self.compute_sha256(p)
        if not hmac.compare_digest(actual_sha.lower(), expected_sha256.lower()):
            raise UpdateVerificationError(
                f"Checksum mismatch: expected {expected_sha256}, got {actual_sha}"
            )

        # 3. Verify Signature
        if not signature:
            raise UpdateVerificationError("Missing update signature")

        # Try Ed25519 verification if trusted public key is configured
        if self.trusted_public_key is not None:
            try:
                sig_bytes = bytes.fromhex(signature)
                payload_bytes = p.read_bytes()
                self.trusted_public_key.verify(sig_bytes, payload_bytes)
                return True
            except (InvalidSignature, ValueError) as exc:
                log.warning("ed25519_signature_verification_failed", error=str(exc))
                raise UpdateVerificationError(
                    "Ed25519 cryptographic signature validation failed"
                ) from exc

        # Fallback to HMAC-SHA256 signature
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
        target_version: str | None = None,
        current_version: str | None = None,
        health_check_fn: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Atomically apply update with verification and automatic rollback."""
        curr_path = Path(current_file)
        new_path = Path(new_package)
        backup_path = curr_path.with_suffix(curr_path.suffix + ".backup")

        # 1. Verify integrity, signature, and downgrade protection
        self.verify_package(
            package_path=new_path,
            expected_sha256=expected_sha256,
            signature=signature,
            target_version=target_version,
            current_version=current_version,
        )

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
