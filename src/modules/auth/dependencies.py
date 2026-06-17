"""Auth DI composition — wires repository into AuthService.

Each router declares its own DI functions (CODING_CONVENTIONS §9).
"""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.modules.auth.exceptions import InvalidTokenError
from src.modules.auth.service import AuthService
from src.modules.users.entities import User
from src.modules.users.repository import UserRepository
from src.shared.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_auth_service(
    session: AsyncSession = Depends(get_async_session),
) -> AuthService:
    """FastAPI dependency — yields an ``AuthService`` wired to its repository."""
    user_repository = UserRepository(session)
    return AuthService(user_repository)


async def get_current_user(
    authorization: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Extract and validate the current user from the Authorization header.

    Decodes the JWT access token, looks up the user, and raises
    ``InvalidTokenError`` if the token is invalid or the user is missing.
    """
    try:
        payload = decode_token(authorization)
    except JWTError as exc:
        raise InvalidTokenError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Token is not an access token")

    subject = payload.get("sub")
    if not subject:
        raise InvalidTokenError("Invalid token payload")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(subject)
    if not user:
        raise InvalidTokenError("User not found")

    return user
