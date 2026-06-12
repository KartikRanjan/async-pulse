"""Unit of Work — transaction boundary manager.

The service drives commit/rollback via ``uow.commit()`` / ``uow.rollback()``.
On exception during ``__aexit__``, the session is rolled back automatically.
The session is never committed in ``__aexit__`` — only the service controls commits.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.modules.users.repository import UserRepository


class UnitOfWork:
    """Groups repositories under a single session and manages transaction boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users: UserRepository | None = None

    async def __aenter__(self) -> "UnitOfWork":
        self.users = UserRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: object,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        """Flush and commit all pending changes."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Discard all pending changes."""
        await self.session.rollback()


async def get_unit_of_work(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> AsyncGenerator[UnitOfWork, None]:
    """FastAPI dependency — yields a ``UnitOfWork`` per request."""
    async with UnitOfWork(session) as uow:
        yield uow
