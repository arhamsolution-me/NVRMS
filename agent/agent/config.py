"""Agent configuration settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Agent configuration loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="AGENT_",
    )

    # ── Agent identity ─────────────────────────────────────
    agent_version: str = "0.1.0"
    agent_id: str = ""  # Set after enrolment (Stage 2)

    # ── Hub connection ─────────────────────────────────────
    hub_url: str = "ws://localhost:8000"
    hub_api_url: str = "http://localhost:8000"

    # ── Credentials (set after enrolment) ─────────────────
    agent_token: SecretStr = Field(default="")

    # ── Logging ────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "console"

    # ── Timing ────────────────────────────────────────────
    heartbeat_interval: int = 30
    heartbeat_timeout: int = 90
    reconnect_base_delay: float = 1.0
    reconnect_max_delay: float = 60.0


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    return AgentSettings()
