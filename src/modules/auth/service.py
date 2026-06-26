"""Auth service — authentication and session management use-cases.

Implements Refresh Token Rotation (RTR), concurrent rotation grace periods,
device session limits, and cache-aside storage.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.core.cache import CacheClient
from src.core.settings import get_settings
from src.db.unit_of_work import UnitOfWork
from src.modules.auth.entities import UserSession
from src.modules.auth.exceptions import InvalidCredentialsError, InvalidTokenError
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schemas import TokenPair, TokenRefreshRequest
from src.modules.users.entities import UserStatus
from src.modules.users.exceptions import UserBannedError, UserSuspendedError
from src.modules.users.service import UserService
from src.shared.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)


def _hash_token(token: str) -> str:
    """Return SHA-256 hash of the token for database storage/comparison."""
    return hashlib.sha256(token.encode()).hexdigest()


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
    ) -> TokenPair:
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

        # Enforce device limits: max 5 active sessions
        active_sessions = await self.repo.get_active_sessions_for_user(user.id)
        if len(active_sessions) >= 5:
            # Revoke oldest sessions to bring count to 4 (leaving room for the new one)
            to_revoke = active_sessions[: len(active_sessions) - 4]
            for old_session in to_revoke:
                old_session.revoke()
                await self.repo.update_session(old_session)
                # Await cache invalidations
                await self.cache.delete(f"session:{old_session.id}")

        session_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)

        access_token = create_access_token(user.id, session_id)
        refresh_token = create_refresh_token(user.id, session_id)

        session = UserSession(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=_hash_token(refresh_token),
            expires_at=expires_at,
            device_info=device_info,
            ip_address=ip_address,
        )

        await self.repo.create_session(session)
        await self.uow.commit()

        # Cache warming (fire-and-forget can be used, but awaiting ensures consistency)
        await self.cache.set_json(
            f"session:{session_id}",
            session.to_dict(),
            ttl=self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_token(
        self,
        request: TokenRefreshRequest,
        ip_address: str | None = None,
    ) -> TokenPair:
        """Validate and rotate a refresh token.

        Handles concurrent client request retries within a 10-second grace period.
        Triggers immediate revocation of all sessions if reuse of a rotated token is detected.
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

        incoming_token_hash = _hash_token(request.refresh_token)

        # 1. Grace Period Check: allow a concurrent retry that replays the *exact*
        # token that was just rotated. The cached pair is bound to the hash of the
        # consumed token, so a different (stale) token for the same session falls
        # through to full validation/breach detection instead of being accepted.
        grace_key = f"grace:{session_id}"
        cached_grace_tokens = await self.cache.get_json(grace_key)
        if cached_grace_tokens and cached_grace_tokens.get("consumed_token_hash") == (
            incoming_token_hash
        ):
            return TokenPair(
                access_token=cached_grace_tokens["access_token"],
                refresh_token=cached_grace_tokens["refresh_token"],
            )

        # 2. Retrieve session (Cache-aside: Redis -> DB)
        session_key = f"session:{session_id}"
        session_data = await self.cache.get_json(session_key)

        if session_data:
            session = UserSession.from_dict(session_data)
        else:
            session = await self.repo.get_session_by_id(session_id)
            if session:
                # Warm the cache
                await self.cache.set_json(
                    session_key,
                    session.to_dict(),
                    ttl=self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                )

        if not session:
            raise InvalidTokenError("Session not found")

        # 3. Breach Detection (RTR Token Reuse)
        token_hash = incoming_token_hash
        if session.is_revoked:
            # If the session was already revoked and the incoming token is
            # NOT the current active one, it indicates a leaked/stale refresh
            # token is being replayed. Immediately revoke all active sessions.
            active_sessions = await self.repo.get_active_sessions_for_user(user_id)
            for act_sess in active_sessions:
                act_sess.revoke()
                await self.repo.update_session(act_sess)
                await self.cache.delete(f"session:{act_sess.id}")
                await self.cache.delete(f"grace:{act_sess.id}")

            await self.uow.commit()
            raise InvalidTokenError("Token reuse detected. All sessions revoked.")

        if session.is_expired:
            raise InvalidTokenError("Refresh token has expired")

        # Verify hash matches the current stored hash
        if session.refresh_token_hash != token_hash:
            raise InvalidTokenError("Invalid refresh token")

        # Validate user status
        user = await self.users.get_user_by_id(user_id)
        if not user or user.status == UserStatus.BANNED or user.status == UserStatus.SUSPENDED:
            raise InvalidTokenError("User account is inactive or blocked")

        # 4. Atomic Rotation
        # Revoke the old session
        session.revoke()
        await self.repo.update_session(session)
        await self.cache.delete(session_key)

        # Create new session
        new_session_id = str(uuid.uuid4())
        # The new session inherits the remaining TTL of the rotation chain
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        remaining_ttl = max(int((expires_at - datetime.now(UTC)).total_seconds()), 0)

        new_access_token = create_access_token(user_id, new_session_id)
        new_refresh_token = create_refresh_token(user_id, new_session_id)

        new_session = UserSession(
            session_id=new_session_id,
            user_id=user_id,
            refresh_token_hash=_hash_token(new_refresh_token),
            expires_at=session.expires_at,
            # device_info is inherited unchanged: the physical device does not
            # change across a rotation. ip_address, by contrast, is taken from
            # the current request because the client's network location can move.
            device_info=session.device_info,
            ip_address=ip_address,
            previous_session_id=session.id,
            rotation_counter=session.rotation_counter + 1,
        )

        await self.repo.create_session(new_session)
        await self.uow.commit()

        # Set new session in cache
        await self.cache.set_json(
            f"session:{new_session_id}",
            new_session.to_dict(),
            ttl=remaining_ttl,
        )

        # Cache the new token pair in the grace period cache under the OLD session
        # ID (valid for 10s). The consumed token hash is stored so only a replay of
        # the exact rotated token is served the cached pair (see grace check above).
        new_tokens = TokenPair(access_token=new_access_token, refresh_token=new_refresh_token)
        await self.cache.set_json(
            grace_key,
            {**new_tokens.model_dump(), "consumed_token_hash": token_hash},
            ttl=10,
        )

        return new_tokens

    async def logout(self, session_id: str) -> None:
        """Revoke a single active session."""
        session = await self.repo.get_session_by_id(session_id)
        if session:
            session.revoke()
            await self.repo.update_session(session)
            await self.uow.commit()

            # Await cache invalidations
            await self.cache.delete(f"session:{session_id}")
            await self.cache.delete(f"grace:{session_id}")

    async def logout_all(self, user_id: str) -> None:
        """Revoke all sessions for a user."""
        active_sessions = await self.repo.get_active_sessions_for_user(user_id)

        await self.repo.revoke_all_sessions(user_id)
        await self.uow.commit()

        # Await cache invalidations for all active sessions
        for session in active_sessions:
            await self.cache.delete(f"session:{session.id}")
            await self.cache.delete(f"grace:{session.id}")
