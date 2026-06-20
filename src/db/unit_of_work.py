"""Unit of Work — thin transaction boundary manager.

The service drives commit/rollback via ``uow.commit()`` / ``uow.rollback()``.
Repositories are composed separately via ``dependencies.py``, sharing the
same session through FastAPI's per-request caching.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session


class UnitOfWork:
    """Wraps a session to provide explicit commit/rollback boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        """Commit all pending changes."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Discard all pending changes."""
        await self.session.rollback()


async def get_unit_of_work(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[UnitOfWork, None]:
    """FastAPI dependency — yields a ``UnitOfWork`` per request."""
    yield UnitOfWork(session)
