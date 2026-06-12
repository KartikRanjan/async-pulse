"""Auth DI composition — wires repository into AuthService.

Each router declares its own DI functions (CODING_CONVENTIONS §9).
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.modules.auth.service import AuthService
from src.modules.users.repository import UserRepository


async def get_auth_service(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> AuthService:
    """FastAPI dependency — yields an ``AuthService`` wired to its repository."""
    user_repository = UserRepository(session)
    return AuthService(user_repository)
