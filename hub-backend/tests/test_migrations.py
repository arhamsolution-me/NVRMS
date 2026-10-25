"""Test that alembic migrations apply and roll back cleanly."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def get_alembic_config(db_url: str) -> Config:
    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(base_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migrations_apply_and_rollback(tmp_path: Path) -> None:
    """Alembic migrations must apply to head and downgrade to base cleanly."""
    # Use a file-based SQLite database for migration test
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    cfg = get_alembic_config(db_url)

    # 1. Upgrade to head
    command.upgrade(cfg, "head")

    # 2. Downgrade to base
    command.downgrade(cfg, "base")

    # 3. Upgrade to head again (idempotent re-run)
    command.upgrade(cfg, "head")
