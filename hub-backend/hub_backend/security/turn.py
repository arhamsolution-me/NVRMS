"""TURN server (coturn) credentials generator and hardening utilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from typing import Any

from hub_backend.config import get_settings


def generate_turn_credentials(
    user_id: uuid.UUID,
    ttl_seconds: int = 3600,
    realm: str = "nvrsms.local",
) -> dict[str, Any]:
    """Generate time-limited HMAC-SHA1 credentials for coturn using the REST API auth secret.

    Format:
        username = "<expiry_unix_timestamp>:<user_id>"
        password = base64(HMAC-SHA1(secret, username))
    """
    settings = get_settings()
    secret = settings.secret_key.get_secret_value().encode("utf-8")

    expiry_time = int(time.time()) + ttl_seconds
    username = f"{expiry_time}:{user_id}"

    mac = hmac.new(secret, username.encode("utf-8"), hashlib.sha1)
    password = base64.b64encode(mac.digest()).decode("utf-8")

    return {
        "username": username,
        "password": password,
        "realm": realm,
        "ttl": ttl_seconds,
        "uris": [
            "turns:turn.nvrsms.local:5349?transport=tcp",
            "turn:turn.nvrsms.local:3478?transport=udp",
            "turn:turn.nvrsms.local:3478?transport=tcp",
        ],
    }


def verify_turn_credentials(
    username: str,
    password: str,
    skew_tolerance_seconds: int = 300,
) -> bool:
    """Validate coturn HMAC credential format and expiration."""
    try:
        parts = username.split(":", 1)
        if len(parts) != 2:
            return False
        expiry_ts = int(parts[0])

        now = int(time.time())
        if now > (expiry_ts + skew_tolerance_seconds):
            # Expired
            return False

        settings = get_settings()
        secret = settings.secret_key.get_secret_value().encode("utf-8")
        mac = hmac.new(secret, username.encode("utf-8"), hashlib.sha1)
        expected_password = base64.b64encode(mac.digest()).decode("utf-8")

        return hmac.compare_digest(password, expected_password)
    except Exception:
        return False
