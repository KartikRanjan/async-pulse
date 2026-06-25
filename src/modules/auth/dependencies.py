"""Auth DI composition and security dependencies.

Implements the token verification pipeline, cache-aside session/identity checks,
and hierarchical Role-Based Access Control (RBAC) guards.
"""

from datetime import datetime

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import CacheClient, get_cache_client
from src.db.session import get_async_session
from src.db.unit_of_work import UnitOfWork, get_unit_of_work
from src.modules.auth.entities import UserSession
from src.modules.auth.exceptions import InvalidTokenError
from src.modules.auth.repository import AuthRepository
from src.modules.auth.service import AuthService, AuthServiceDeps
from src.modules.users.dependencies import get_user_service
from src.modules.users.entities import User, UserRole, UserStatus
from src.modules.users.exceptions import InsufficientPermissionsError
from src.modules.users.service import UserService
from src.shared.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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


async def get_current_user(
    authorization: str = Depends(oauth2_scheme),
    auth_repo: AuthRepository = Depends(get_auth_repository),
    user_service: UserService = Depends(get_user_service),
    cache: CacheClient = Depends(get_cache_client),
) -> User:
    """Extract and validate the current user session and identity from token.

    Decodes JWT access token, checks session active state in cache/DB,
    validates user account status (rejects suspended/banned/unverified),
    and retrieves user profile via cache-aside lookup.
    """
    try:
        payload = decode_token(authorization)
    except JWTError as exc:
        raise InvalidTokenError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Token is not an access token")

    user_id = payload.get("sub")
    session_id = payload.get("sid")
    if not user_id or not session_id:
        raise InvalidTokenError("Invalid token payload")

    # 1. Verify session validity (Cache-aside: Redis -> DB)
    session_key = f"session:{session_id}"
    session_data = await cache.get_json(session_key)

    if session_data:
        session = UserSession.from_dict(session_data)
    else:
        session = await auth_repo.get_session_by_id(session_id)
        if session:
            # Warm cache
            await cache.set_json(session_key, session.to_dict(), ttl=3600)

    if not session or not session.is_active:
        raise InvalidTokenError("Session is invalid or has been logged out")

    # 2. Retrieve user identity/status (Cache-aside: Redis -> DB)
    user_key = f"user:{user_id}"
    user_dict = await cache.get_json(user_key)

    if user_dict:
        # Reconstruct User from cache data
        user = User(
            user_id=user_dict["id"],
            email=user_dict["email"],
            username=user_dict["username"],
            hashed_password=user_dict["hashed_password"],
            status=UserStatus(user_dict["status"]),
            role=UserRole(user_dict["role"]),
            deleted_at=datetime.fromisoformat(user_dict["deleted_at"])
            if user_dict.get("deleted_at")
            else None,
            created_at=datetime.fromisoformat(user_dict["created_at"])
            if user_dict.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(user_dict["updated_at"])
            if user_dict.get("updated_at")
            else None,
        )
    else:
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise InvalidTokenError("User profile not found")
        # Warm cache
        await cache.set_json(
            user_key,
            {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "hashed_password": user.hashed_password,
                "status": user.status,
                "role": user.role,
                "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            },
            ttl=3600,
        )

    # 3. Check status machine states
    if user.status == UserStatus.PENDING_VERIFICATION:
        raise InvalidTokenError("User email verification is pending")
    if user.status == UserStatus.SUSPENDED:
        raise InvalidTokenError("User account has been suspended")
    if user.status == UserStatus.BANNED:
        raise InvalidTokenError("User account has been banned")

    # Store session id on current user request object if needed
    # (or simply return user entity)
    return user


class RoleGuard:
    """FastAPI dependency callable for hierarchical RBAC authorization."""

    def __init__(self, required_role: UserRole) -> None:
        self.required_role = required_role

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        """Enforce role check dependency validation."""
        role_hierarchy = {
            UserRole.USER: 1,
            UserRole.ADMIN: 2,
            UserRole.SUPERUSER: 3,
        }
        current_val = role_hierarchy.get(current_user.role, 0)
        required_val = role_hierarchy.get(self.required_role, 0)

        if current_val < required_val:
            raise InsufficientPermissionsError(
                f"Requires at least {self.required_role} role permissions"
            )
        return current_user


def require_role(role: UserRole) -> RoleGuard:
    """Return a security dependency requiring the given hierarchical role."""
    return RoleGuard(role)
