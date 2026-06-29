"""Auth service — authentication and session management use-cases.

Implements Refresh Token Rotation (RTR), concurrent rotation grace periods,
device session limits, and cache-aside storage.
"""

import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.core.cache import CacheClient
from src.core.settings import get_settings
from src.db.unit_of_work import UnitOfWork
from src.modules.auth.entities import SessionValidation, UserSession
from src.modules.auth.exceptions import InvalidCredentialsError, InvalidTokenError
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schemas import LoginResponse, TokenPair, TokenRefreshRequest, UserInfo
from src.modules.users.entities import UserStatus
from src.modules.users.exceptions import UserBannedError, UserSuspendedError
from src.modules.users.service import UserService
from src.shared.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

# Grace window for benign concurrent rotation races (DB timestamp is the gate,
# Redis is only used for smooth token replay within this window).
_GRACE_WINDOW_MS = 30_000  # 30 seconds


@dataclass(frozen=True)
class AuthServiceDeps:
    """Collaborators for ``AuthService`` (grouped per the 3+ dependency rule)."""

    repository: AuthRepository
    user_service: UserService
    uow: UnitOfWork
    cache: CacheClient


class AuthService:
    """Orchestrates login, token refresh, and logout session flows."""

    def __init__(self, deps: AuthServiceDeps) -> None:
        self.repo = deps.repository
        self.users = deps.user_service
        self.uow = deps.uow
        self.cache = deps.cache
        self.settings = get_settings()

    async def authenticate(
        self,
        email: str,
        password: str,
        device_info: str | None = None,
        ip_address: str | None = None,
    ) -> LoginResponse:
        """Verify login credentials and issue a new session with rotated tokens."""
        user = await self.users.get_user_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()

        # Check account status state invariants
        if user.status == UserStatus.SUSPENDED:
            raise UserSuspendedError()
        if user.status == UserStatus.BANNED:
            raise UserBannedError()
        # Note: we allow PENDING_VERIFICATION to login but restrict actions via dependencies

        # Enforce device limits: max 5 active sessions (already sorted oldest-first by repo)
        active_sessions = await self.repo.get_active_sessions_for_user(user.id)
        if len(active_sessions) >= 5:
            # Revoke oldest sessions to bring count to 4 (leaving room for the new one)
            to_revoke = active_sessions[: len(active_sessions) - 4]
            for old_session in to_revoke:
                old_session.revoke()
                await self.repo.update_session(old_session)
                with suppress(Exception):
                    await self.cache.delete(f"session:{old_session.id}")

        session_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)

        access_token = create_access_token(user.id, session_id)
        refresh_token = create_refresh_token(user.id, session_id)

        session = UserSession(
            session_id=session_id,
            user_id=user.id,
            expires_at=expires_at,
            device_info=device_info,
            ip_address=ip_address,
        )

        await self.repo.create_session(session)
        await self.uow.commit()

        # Cache warming — best-effort, never crash the login path
        with suppress(Exception):
            await self.cache.set_json(
                f"session:{session_id}",
                SessionValidation.from_session(session).to_dict(),
                ttl=self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            )

        return LoginResponse(
            token_pair=TokenPair(
                access_token=access_token,
                refresh_token=refresh_token,
            ),
            user_info=UserInfo(
                user_id=user.id,
                email=user.email,
                name=user.name,
                username=user.username,
                role=str(user.role),
            ),
        )

    async def refresh_token(
        self,
        request: TokenRefreshRequest,
        ip_address: str | None = None,
    ) -> TokenPair:
        """Validate and rotate a refresh token.

        Grace period logic:
        - The DB ``revoked_at`` timestamp is the source of truth for the
          benign-vs-breach decision. A Redis outage can never trigger a
          false ``logout_all``.
        - Within the 30-second grace window (measured from ``revoked_at``),
          a concurrent retry is treated as a benign race. Redis is checked
          for the cached new pair to return identical tokens to both callers.
          A Redis miss in the grace window returns a safe 401 ('please retry'),
          never a ``logout_all``.
        - Outside the grace window a revoked token is definitively a breach:
          all user sessions are revoked atomically via ``logout_all``.
        """
        try:
            payload = decode_token(request.refresh_token)
        except Exception as exc:
            raise InvalidTokenError("Invalid or expired refresh token") from exc

        if payload.get("type") != "refresh":
            raise InvalidTokenError("Token is not a refresh token")

        session_id = payload.get("jti")
        user_id = payload.get("sub")
        if not session_id or not user_id:
            raise InvalidTokenError("Invalid token payload")

        grace_key = f"grace:{session_id}"
        session_key = f"session:{session_id}"

        # 1. Read the authoritative session row from the DB.
        # Rotation is a write/security-critical path that runs at most once per
        # access-token lifetime, so we never trust the cache projection here:
        # the DB ``revoked_at`` must be the source of truth for the
        # benign-vs-breach decision below, and the full row carries the
        # device_info / chain metadata the new session inherits.
        session = await self.repo.get_session_by_id(session_id)
        if not session:
            raise InvalidTokenError("Session not found")

        # 2. Revoked row — DB timestamp decides benign vs breach
        if session.is_revoked:
            revoked_at = session.revoked_at
            assert revoked_at is not None  # is_revoked guarantees this
            if revoked_at.tzinfo is None:
                revoked_at = revoked_at.replace(tzinfo=UTC)

            revoked_ago_ms = (datetime.now(UTC) - revoked_at).total_seconds() * 1000

            if revoked_ago_ms <= _GRACE_WINDOW_MS:
                # Within the grace window: benign concurrent race.
                # Redis replay is a UX optimization only — a miss here is a safe
                # 401 (client retries), never a logout_all.
                cached = None
                with suppress(Exception):
                    cached = await self.cache.get_json(grace_key)

                if cached:
                    return TokenPair(
                        access_token=str(cached["access_token"]),
                        refresh_token=str(cached["refresh_token"]),
                    )
                raise InvalidTokenError("Concurrent refresh — please retry")

            # Outside grace window → genuine token reuse → breach
            await self.logout_all(user_id)
            raise InvalidTokenError("Token reuse detected. All sessions revoked.")

        if session.is_expired:
            raise InvalidTokenError("Refresh token has expired")

        # 3. Validate user status
        user = await self.users.get_user_by_id(user_id)
        if not user or user.status == UserStatus.BANNED or user.status == UserStatus.SUSPENDED:
            raise InvalidTokenError("User account is inactive or blocked")

        # 4. Atomic rotation — revoke old session, create new one
        session.revoke()
        await self.repo.update_session(session)
        with suppress(Exception):
            await self.cache.delete(session_key)

        # Cap new JWT expiry to the chain's original window (Fix 2).
        # This prevents the JWT from outliving the DB session row near the end
        # of a long rotation chain.
        chain_expires_at = session.expires_at
        if chain_expires_at.tzinfo is None:
            chain_expires_at = chain_expires_at.replace(tzinfo=UTC)
        remaining_seconds = max(int((chain_expires_at - datetime.now(UTC)).total_seconds()), 0)

        new_session_id = str(uuid.uuid4())
        new_access_token = create_access_token(user_id, new_session_id)
        new_refresh_token = create_refresh_token(
            user_id, new_session_id, expires_in=remaining_seconds
        )

        new_session = UserSession(
            session_id=new_session_id,
            user_id=user_id,
            expires_at=chain_expires_at,
            # device_info is inherited unchanged: the physical device does not
            # change across a rotation. ip_address is taken fresh from the current
            # request because the client's network location can move.
            device_info=session.device_info,
            ip_address=ip_address,
            previous_session_id=session.id,
        )

        await self.repo.create_session(new_session)
        await self.uow.commit()

        # Cache new session — best-effort
        with suppress(Exception):
            await self.cache.set_json(
                f"session:{new_session_id}",
                SessionValidation.from_session(new_session).to_dict(),
                ttl=remaining_seconds,
            )

        new_tokens = TokenPair(access_token=new_access_token, refresh_token=new_refresh_token)

        # Write grace entry keyed by OLD jti so concurrent losers can replay the
        # same pair within the grace window. Written AFTER commit so the DB row
        # is already revoked before any retry could hit the breach path.
        with suppress(Exception):
            await self.cache.set_json(
                grace_key,
                new_tokens.model_dump(),
                ttl=int(_GRACE_WINDOW_MS / 1000),
            )

        return new_tokens

    async def logout(self, session_id: str) -> None:
        """Revoke a single active session."""
        session = await self.repo.get_session_by_id(session_id)
        if session:
            session.revoke()
            await self.repo.update_session(session)
            await self.uow.commit()

            with suppress(Exception):
                await self.cache.delete(f"session:{session_id}")
            with suppress(Exception):
                await self.cache.delete(f"grace:{session_id}")

    async def logout_all(self, user_id: str) -> None:
        """Revoke all sessions for a user."""
        active_sessions = await self.repo.get_active_sessions_for_user(user_id)

        await self.repo.revoke_all_sessions(user_id)
        await self.uow.commit()

        for session in active_sessions:
            with suppress(Exception):
                await self.cache.delete(f"session:{session.id}")
            with suppress(Exception):
                await self.cache.delete(f"grace:{session.id}")
