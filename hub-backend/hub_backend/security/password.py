"""Argon2id password hashing, verification, timing-attack defense, and password strength policy."""

from __future__ import annotations

import contextlib
import re

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

# Pre-computed dummy hash used to equalize execution timing when email is not found
_DUMMY_HASH = _hasher.hash("dummy_constant_time_comparison_string_123456789")

# Top common breached passwords list for blacklist validation
BREACHED_PASSWORDS = frozenset(
    {
        "password",
        "password123",
        "password123!",
        "123456789012",
        "admin123456!",
        "welcome1234!",
        "qwerty123456!",
        "letmein12345!",
        "superadmin123",
        "changeme1234!",
        "cctvadmin123!",
        "iloveyou1234!",
    }
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


def dummy_verify(plain_password: str) -> None:
    """Perform constant-time dummy Argon2id verification to prevent user enumeration timing attacks."""
    with contextlib.suppress(Exception):
        _hasher.verify(_DUMMY_HASH, plain_password)


def check_password_strength(password: str) -> tuple[bool, str | None]:
    """Validate password against complexity policy and breached password dictionary.

    Policy:
        - At least 12 characters.
        - Contains uppercase, lowercase, digit, and symbol.
        - Not in common breached passwords list.
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters long"

    if password.lower() in BREACHED_PASSWORDS:
        return False, "Password has appeared in known data breaches and cannot be used"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one digit"

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"

    return True, None


def needs_rehash(hashed_password: str) -> bool:
    """Check if the hash needs to be upgraded to current parameters."""
    return _hasher.check_needs_rehash(hashed_password)
