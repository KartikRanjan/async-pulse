"""Shared test fixtures for the entire test suite.

Uses an in-memory SQLite database for isolation and speed.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import close_all_sessions

from src.db.base import Base
from src.db.session import get_async_session
from src.main import app

# ── In-memory test engine ─────────────────────────────────

test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
test_session_factory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Database fixtures ─────────────────────────────────────



@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh database session and roll back after the test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        yield session
        await session.rollback()

    close_all_sessions()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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

