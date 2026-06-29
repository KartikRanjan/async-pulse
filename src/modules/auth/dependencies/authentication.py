"""Authentication — proving *who you are*.

This is the auth gate consumed by every protected route across all modules
(the FastAPI equivalent of an Express ``authenticate`` middleware):

- ``oauth2_scheme``: extracts the bearer token from the Authorization header
- ``get_current_user``: token → session → identity → status validation
- ``CurrentUserDep``: ready-to-use ``Annotated`` alias for clean route signatures

Authorization ("what you are allowed to do" — RBAC) lives in ``.permissions``.
Service/repository wiring lives in ``.providers``.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from src.core.cache import CacheClient, get_cache_client
from src.core.settings import get_settings
from src.modules.auth.entities import SessionValidation
from src.modules.auth.exceptions import InvalidTokenError
from src.modules.auth.repository import AuthRepository
from src.modules.users.dependencies import get_user_service
from src.modules.users.entities import User, UserRole, UserStatus
from src.modules.users.service import UserService
from src.shared.security import decode_token

from .providers import get_auth_repository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{get_settings().API_V1_PREFIX}/auth/login")


async def get_current_user(
    authorization: str = Depends(oauth2_scheme),
    auth_repo: AuthRepository = Depends(get_auth_repository),
    user_service: UserService = Depends(get_user_service),
    cache: CacheClient = Depends(get_cache_client),
) -> User:
    """Authenticate the request: validate token, session, and user status.

    Decodes the JWT access token, checks session active state in cache/DB,
    validates user account status (rejects suspended/banned/unverified),
    and retrieves the user profile via cache-aside lookup.
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
        session = SessionValidation.from_dict(session_data)
    else:
        full_session = await auth_repo.get_session_by_id(session_id)
        if full_session:
            session = SessionValidation.from_session(full_session)
            # Warm cache with the validation projection only
            await cache.set_json(session_key, session.to_dict(), ttl=3600)
        else:
            session = None

    if not session or not session.is_active:
        raise InvalidTokenError("Session is invalid or has been logged out")

    # Defence-in-depth: the session must belong to the user claimed by the token.
    # Prevents a mismatched sid→sub pairing being accepted (cross-user session use).
    if session.user_id != user_id:
        raise InvalidTokenError("Session does not belong to this user")

    # 2. Retrieve user identity/status (Cache-aside: Redis -> DB).
    #
    # Caching identity here is safe for the security gate because status changes
    # that must lock a user out (suspend/ban via ``UserService.change_status``
    # and soft-delete via ``delete_user``) revoke that user's sessions and clear
    # their session cache. The session check above is therefore the authoritative
    # lockout point, so a momentarily stale ``user:{id}`` snapshot cannot keep a
    # revoked user authenticated. The status checks below remain as defence in
    # depth (and cover PENDING_VERIFICATION, which does not revoke sessions).
    user_key = f"user:{user_id}"
    user_dict = await cache.get_json(user_key)

    if user_dict:
        # Reconstruct the User from the cached identity projection. Only the
        # fields the auth gate and downstream RBAC need are cached
        # (id, email, status, role); username/timestamps are profile metadata
        # read straight from the DB when a route actually needs them, and the
        # password hash is only needed at login. Blanks are safe here because
        # no authenticated-path consumer reads them off ``current_user``.
        user = User(
            user_id=user_dict["id"],
            email=user_dict["email"],
            username="",
            name="",
            hashed_password="",
            status=UserStatus(user_dict["status"]),
            role=UserRole(user_dict["role"]),
        )
    else:
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise InvalidTokenError("User profile not found")
        # Warm cache with the minimal identity projection (matches the documented
        # ``user:{uid}`` contract: id, email, status, role).
        await cache.set_json(
            user_key,
            {
                "id": user.id,
                "email": user.email,
                "status": user.status,
                "role": user.role,
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

    return user


# Ready-to-use dependency alias so routes read cleanly across modules.
CurrentUserDep = Annotated[User, Depends(get_current_user)]
