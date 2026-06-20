"""User DI composition — wires repository + UoW into UserService.

Each router declares its own DI functions (CODING_CONVENTIONS §9).
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import CacheClient, get_cache_client
from src.db.session import get_async_session
from src.db.unit_of_work import UnitOfWork, get_unit_of_work
from src.modules.users.repository import UserRepository
from src.modules.users.service import UserService


async def get_user_service(
    session: AsyncSession = Depends(get_async_session),
    uow: UnitOfWork = Depends(get_unit_of_work),
    cache: CacheClient = Depends(get_cache_client),
) -> UserService:
    """FastAPI dependency — yields a ``UserService`` with its repository and UoW."""
    repository = UserRepository(session)
    return UserService(repository=repository, uow=uow, cache=cache)
