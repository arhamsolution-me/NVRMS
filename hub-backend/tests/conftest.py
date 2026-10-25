"""Test configuration and fixtures for hub-backend."""

from __future__ import annotations

import asyncio
import os

# Override settings for tests before any hub_backend imports
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("POSTGRES_PASSWORD", "nvrsms")
os.environ.setdefault("REDIS_PASSWORD", "testpass")
os.environ.setdefault("SUPER_ADMIN_PASSWORD", "SuperAdmin123!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("APP_ENV", "development")

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hub_backend.db import Base


# ── Test database URL ──────────────────────────────────────────────
def get_test_db_url() -> str:
    """Get test database URL from environment or use a default."""
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://nvrsms:nvrsms@localhost:5432/nvrsms_test",
    )


def get_test_redis_url() -> str:
    return os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1")


# ── Async engine for tests ─────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create async engine pointing at the test database."""
    engine = create_async_engine(
        get_test_db_url(),
        echo=False,
        pool_pre_ping=True,
    )
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional session that rolls back after each test."""
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client pointed at the FastAPI app."""
    # Override settings for tests
    os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long")
    os.environ.setdefault("POSTGRES_PASSWORD", "nvrsms")
    os.environ.setdefault("REDIS_PASSWORD", "testpass")
    os.environ.setdefault("SUPER_ADMIN_PASSWORD", "SuperAdmin123!")
    os.environ.setdefault("DATABASE_URL", get_test_db_url())
    os.environ.setdefault("REDIS_URL", get_test_redis_url())
    os.environ.setdefault("APP_ENV", "development")

    from hub_backend.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from hub_backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
