"""Shared test fixtures for the entire test suite.

Uses an in-memory SQLite database for isolation and speed.
"""

# ruff: noqa: E402 — env vars must be set before Settings() is called

import os

os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-at-least-32-characters-long"  # noqa: S105
os.environ["DEBUG"] = "false"
os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_async_pulse.db"
os.environ["DB_SCHEMA"] = ""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import close_all_sessions

from src.core.settings import get_settings
from src.db.base import Base
from src.db.session import get_async_session

get_settings.cache_clear()

from sqlalchemy.pool import StaticPool

from src.main import app

# ── Database fixtures ─────────────────────────────────────


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh database session and roll back after the test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()

    close_all_sessions()
    await engine.dispose()



@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an ``AsyncClient`` wired to the test database."""

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
