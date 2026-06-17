"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

Create the engine and session factory as module-level singletons (CODING_CONVENTIONS §16).
``get_async_session`` is a FastAPI dependency that yields one session per request.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.settings import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields one ``AsyncSession`` per request."""
    async with async_session_factory() as session:
        yield session
