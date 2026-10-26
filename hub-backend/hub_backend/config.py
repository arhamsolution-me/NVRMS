"""NVRSMS Hub Backend — Application Configuration.

All settings are loaded from environment variables (or .env file).
Never log or expose these values.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_version: str = "0.1.0"

    # ── Security ───────────────────────────────────────────
    secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ── Database ───────────────────────────────────────────
    database_url: str = Field(default="postgresql+asyncpg://nvrsms:nvrsms@localhost:5432/nvrsms")

    # ── Redis ──────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── CORS ───────────────────────────────────────────────
    allowed_origins: str | list[str] = ["http://localhost:5173"]

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            import json
            if v.startswith("[") and v.endswith("]"):
                try:
                    return [str(x) for x in json.loads(v)]
                except Exception:
                    pass
            return [o.strip() for o in v.split(",") if o.strip()]
        return list(v)

    # ── Logging ────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ── MediaMTX ──────────────────────────────────────────
    mediamtx_api_url: str = "http://localhost:9997"

    # ── Rate limiting ─────────────────────────────────────
    rate_limit_login: str = "5/minute"

    # ── Super admin seed ──────────────────────────────────
    super_admin_email: str = "admin@nvrsms.local"
    super_admin_password: SecretStr = Field(default=SecretStr("changeme123!"))

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
