"""Argon2id password hashing and verification."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id password hasher with secure production parameters
# RFC 9106 recommended: time_cost=2, memory_cost=65536 (64 MiB), parallelism=1
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2id hash. Returns True on success, False on mismatch."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Check if the hash needs to be upgraded to current parameters."""
    return _hasher.check_needs_rehash(hashed_password)
