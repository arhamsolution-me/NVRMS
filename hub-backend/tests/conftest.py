"""Test configuration and fixtures for hub-backend."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Generator

# Override settings for tests before any hub_backend imports
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("POSTGRES_PASSWORD", "nvrsms")
os.environ.setdefault("REDIS_PASSWORD", "testpass")
os.environ.setdefault("SUPER_ADMIN_PASSWORD", "SuperAdmin123!")
os.environ.setdefault(
    "TEST_DATABASE_URL", "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"
)
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("APP_ENV", "development")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import hub_backend.models  # noqa: F401
from hub_backend.db import AsyncSessionLocal, Base, get_db
from hub_backend.db import engine as default_engine
from hub_backend.main import app
from hub_backend.security.tokens import create_access_token
from hub_backend.services.seed import seed_initial_data


def get_test_db_url() -> str:
    """Get test database URL."""
    return os.environ.get(
        "TEST_DATABASE_URL",
        "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true",
    )


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create async engine pointing at test database and create all tables."""
    db_url = get_test_db_url()
    engine_kwargs = {"echo": False}
    if not db_url.startswith("sqlite"):
        engine_kwargs["pool_pre_ping"] = True

    hold_conn = None
    if "mode=memory" in db_url:
        import sqlite3

        clean = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        hold_conn = sqlite3.connect(clean, uri=True)

    engine = create_async_engine(db_url, **engine_kwargs)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal.configure(bind=engine)
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await seed_initial_data(session)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    AsyncSessionLocal.configure(bind=default_engine)
    await engine.dispose()
    if hold_conn:
        hold_conn.close()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional session for database operations."""
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session


@pytest.fixture(autouse=True)
def reset_singletons() -> Generator[None, None, None]:
    """Reset in-memory singletons before and after each test."""
    from hub_backend.services.stream_manager import stream_manager

    stream_manager.reset()
    yield
    stream_manager.reset()


@pytest.fixture
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client pointed at the FastAPI app with test DB dependency override."""
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def auth_header_factory():
    """Factory creating Authorization headers with a valid JWT for given user parameters."""

    def _make(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role_id: uuid.UUID,
        is_superuser: bool = False,
    ) -> dict[str, str]:
        token = create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            role_id=role_id,
            is_superuser=is_superuser,
        )
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture(autouse=True)
def reset_rate_limits_between_tests() -> None:
    """Reset sliding-window rate limits before each test run."""
    from hub_backend.security.rate_limit import rate_limiter

    rate_limiter.reset_all()
