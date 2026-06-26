"""Auth DI composition (wiring only).

Builds the auth module's collaborators for injection:
- ``get_auth_repository`` — session persistence
- ``get_auth_service`` — full auth use-case service (login/refresh/logout)

The authentication gate (``get_current_user``, ``oauth2_scheme``) lives in
``.authentication``; authorization (RBAC role guards) lives in
``.permissions``.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import CacheClient, get_cache_client
from src.db.session import get_async_session
from src.db.unit_of_work import UnitOfWork, get_unit_of_work
from src.modules.auth.repository import AuthRepository
from src.modules.auth.service import AuthService, AuthServiceDeps
from src.modules.users.dependencies import get_user_service
from src.modules.users.service import UserService


async def get_auth_repository(
    session: AsyncSession = Depends(get_async_session),
) -> AuthRepository:
    """FastAPI dependency — yields an ``AuthRepository``."""
    return AuthRepository(session)


async def get_auth_service(
    repository: AuthRepository = Depends(get_auth_repository),
    user_service: UserService = Depends(get_user_service),
    uow: UnitOfWork = Depends(get_unit_of_work),
    cache: CacheClient = Depends(get_cache_client),
) -> AuthService:
    """FastAPI dependency — yields an ``AuthService``.

    Identity reads/writes are delegated to ``UserService`` (the users module owns
    the ``users`` table); ``AuthRepository`` provides session persistence only.
    """
    return AuthService(
        deps=AuthServiceDeps(
            repository=repository,
            user_service=user_service,
            uow=uow,
            cache=cache,
        ),
    )
