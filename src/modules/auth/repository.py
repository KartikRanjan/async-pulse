"""Auth repository — data access for authentication sessions.

Owns the ``sessions`` table exclusively (Refresh Token Rotation tracking).
Credential and status access on the ``users`` table is *not* handled here:
the auth module reaches user identity data through ``UserService`` to respect
cross-module isolation (the users module is the sole owner of ``UserModel``).
Never commits — transaction boundaries are managed by the Unit of Work.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.entities import UserSession
from src.modules.auth.models import SessionModel


class AuthRepository:
    """Handles RTR session tracking for the ``sessions`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Session Mapping ───────────────────────────────────

    @staticmethod
    def _to_session_entity(model: SessionModel) -> UserSession:
        return UserSession(
            session_id=model.id,
            user_id=model.user_id,
            expires_at=model.expires_at,
            device_info=model.device_info,
            ip_address=model.ip_address,
            created_at=model.created_at,
            revoked_at=model.revoked_at,
            previous_session_id=model.previous_session_id,
        )

    # ── Session CRUD ──────────────────────────────────────

    async def create_session(self, session: UserSession) -> UserSession:
        """Create and store a new active session."""
        model = SessionModel(
            id=session.id,
            user_id=session.user_id,
            device_info=session.device_info,
            ip_address=session.ip_address,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            previous_session_id=session.previous_session_id,
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_session_entity(model)

    async def get_session_by_id(self, session_id: str) -> UserSession | None:
        """Fetch session by its primary ID."""
        result = await self.session.execute(
            select(SessionModel).where(SessionModel.id == session_id),
        )
        model = result.scalar_one_or_none()
        return self._to_session_entity(model) if model else None

    async def get_active_sessions_for_user(self, user_id: str) -> list[UserSession]:
        """Fetch all active (non-revoked, non-expired) sessions for a user."""
        result = await self.session.execute(
            select(SessionModel)
            .where(
                SessionModel.user_id == user_id,
                SessionModel.revoked_at.is_(None),
                SessionModel.expires_at > datetime.now(UTC),
            )
            .order_by(SessionModel.created_at.asc()),
        )
        models = result.scalars().all()
        return [self._to_session_entity(m) for m in models]

    async def update_session(self, session: UserSession) -> UserSession:
        """Update session state (e.g. revoke or rotate token).

        Uses ``Session.merge`` so the already-mutated entity held by the service
        is reconciled in a single round-trip, avoiding a redundant SELECT when
        the row is already in the identity map.
        """
        model = SessionModel(
            id=session.id,
            user_id=session.user_id,
            device_info=session.device_info,
            ip_address=session.ip_address,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            previous_session_id=session.previous_session_id,
        )
        merged = await self.session.merge(model)
        await self.session.flush()
        return self._to_session_entity(merged)

    async def revoke_all_sessions(self, user_id: str) -> None:
        """Revoke all sessions for a user (force logout everywhere)."""
        result = await self.session.execute(
            select(SessionModel).where(
                SessionModel.user_id == user_id,
                SessionModel.revoked_at.is_(None),
            ),
        )
        models = result.scalars().all()
        now = datetime.now(UTC)
        for model in models:
            model.revoked_at = now
        await self.session.flush()
