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
    """FastAPI dependency — yields a ``UserService`` with its repository and UoW.

    The auth-backed session revoker is composed here so status-lockout
    operations (suspend/ban/delete) can terminate active sessions. The auth
    import is deferred to call time because the auth module depends on the users
    module; importing it lazily at the composition root avoids a load-time cycle.
    """
    from src.modules.auth import build_session_revoker

    repository = UserRepository(session)
    session_revoker = build_session_revoker(session, cache)
    return UserService(
        repository=repository,
        uow=uow,
        cache=cache,
        session_revoker=session_revoker,
    )
