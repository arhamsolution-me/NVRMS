"""Edge Agent diagnostics bundle with strict credential sanitization."""

from __future__ import annotations

import os
import platform
import re
import sys
from datetime import UTC, datetime
from typing import Any

from agent.config import get_settings
from agent.resilience.disk_monitor import disk_monitor
from agent.resilience.time_sync import time_sync_manager
from agent.streaming.manager import agent_stream_manager

REDACTION_PATTERNS = [
    # RTSP URLs with embedded user:pass: rtsp://user:pass@host...
    re.compile(
        r"(rtsp://)([^:/\s]+):([^\s\"'<>]+)@([a-zA-Z0-9_.-]+(?::\d+)?(?:/[^\s\"'<>]*)?)",
        re.IGNORECASE,
    ),
    # JWT tokens: eyJ...
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # Bearer tokens
    re.compile(r"(Bearer\s+)[A-Za-z0-9_.-]+", re.IGNORECASE),
    # Fernet / Base64 keys
    re.compile(r"[A-Za-z0-9+/=]{44}"),
]

SENSITIVE_KEY_NAMES = {
    "password",
    "token",
    "secret",
    "key",
    "authorization",
    "enrolment_code",
    "agent_token",
    "private_key",
    "pass",
}


class DiagnosticsCollector:
    """Collects system, streaming, and network diagnostics with credential redaction."""

    def sanitize_string(self, text: str) -> str:
        """Sanitize text by replacing sensitive patterns."""
        sanitized = text
        for pat in REDACTION_PATTERNS:
            if "rtsp://" in pat.pattern:
                sanitized = pat.sub(r"\1***REDACTED***:***REDACTED***@\4", sanitized)
            else:
                sanitized = pat.sub("***REDACTED***", sanitized)
        return sanitized

    def sanitize_data(self, data: Any) -> Any:
        """Recursively redact secrets from dicts, lists, and primitives."""
        if isinstance(data, dict):
            cleaned: dict[str, Any] = {}
            for k, v in data.items():
                if any(sens in k.lower() for sens in SENSITIVE_KEY_NAMES):
                    cleaned[k] = "***REDACTED***"
                else:
                    cleaned[k] = self.sanitize_data(v)
            return cleaned

        if isinstance(data, list):
            return [self.sanitize_data(item) for item in data]

        if isinstance(data, str):
            return self.sanitize_string(data)

        return data

    def collect_bundle(self) -> dict[str, Any]:
        """Generate comprehensive, sanitized diagnostics bundle."""
        settings = get_settings()

        bundle = {
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_version": settings.agent_version,
            "system": {
                "os": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python_version": sys.version.split()[0],
                "cpu_count": os.cpu_count() or 1,
            },
            "disk": disk_monitor.get_disk_stats("."),
            "time_sync": {
                "is_skewed": time_sync_manager.is_skewed,
                "skew_seconds": round(time_sync_manager.skew_seconds, 2),
                "last_sync": (
                    time_sync_manager.last_sync_time.isoformat()
                    if time_sync_manager.last_sync_time
                    else None
                ),
            },
            "active_streams": agent_stream_manager.list_active(),
            "config": {
                "hub_url": settings.hub_url,
                "heartbeat_interval": settings.heartbeat_interval,
                "log_level": settings.log_level,
            },
        }

        # Apply comprehensive recursive sanitization
        return self.sanitize_data(bundle)


diagnostics_collector = DiagnosticsCollector()
