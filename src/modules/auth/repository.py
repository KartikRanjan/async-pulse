"""Auth repository — data access for authentication identities and sessions.

Enforces field privilege separation: only reads/writes credential and security
fields from the ``users`` table, and completely manages the ``sessions`` table.
Never commits — transaction boundaries are managed by the Unit of Work.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.entities import AuthIdentity, UserSession
from src.modules.auth.models import SessionModel
from src.modules.users.models import UserModel


class AuthRepository:
    """Handles credentials access and RTR session tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Identity Mapping ──────────────────────────────────

    @staticmethod
    def _to_identity(model: UserModel) -> AuthIdentity:
        return AuthIdentity(
            user_id=model.id,
            email=model.email,
            username=model.username,
            hashed_password=model.hashed_password,
            status=model.status,
            role=model.role,
            deleted_at=model.deleted_at,
        )

    # ── Identity Queries & Writes ─────────────────────────

    async def get_identity_by_email(self, email: str) -> AuthIdentity | None:
        """Fetch credentials identity by email."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email),
        )
        model = result.scalar_one_or_none()
        return self._to_identity(model) if model else None

    async def get_identity_by_id(self, user_id: str) -> AuthIdentity | None:
        """Fetch credentials identity by user ID."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id),
        )
        model = result.scalar_one_or_none()
        return self._to_identity(model) if model else None

    async def update_identity(self, identity: AuthIdentity, **fields: object) -> AuthIdentity:
        """Update identity credential/status fields. Enforces privilege separation."""
        forbidden = {"email", "username", "created_at"}
        if any(f in fields for f in forbidden):
            raise TypeError("AuthRepository cannot modify profile/persona fields (email, username)")

        result = await self.session.execute(
            select(UserModel).where(UserModel.id == identity.id),
        )
        model = result.scalar_one()
        for key, value in fields.items():
            setattr(model, key, value)
        model.updated_at = datetime.now(UTC)
        await self.session.flush()
        return self._to_identity(model)

    # ── Session Mapping ───────────────────────────────────

    @staticmethod
    def _to_session_entity(model: SessionModel) -> UserSession:
        return UserSession(
            session_id=model.id,
            user_id=model.user_id,
            refresh_token_hash=model.refresh_token_hash,
            expires_at=model.expires_at,
            device_info=model.device_info,
            ip_address=model.ip_address,
            created_at=model.created_at,
            revoked_at=model.revoked_at,
            previous_session_id=model.previous_session_id,
            rotation_counter=model.rotation_counter,
        )

    # ── Session CRUD ──────────────────────────────────────

    async def create_session(self, session: UserSession) -> UserSession:
        """Create and store a new active session."""
        model = SessionModel(
            id=session.id,
            user_id=session.user_id,
            refresh_token_hash=session.refresh_token_hash,
            device_info=session.device_info,
            ip_address=session.ip_address,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            previous_session_id=session.previous_session_id,
            rotation_counter=session.rotation_counter,
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
        """Update session state (e.g. revoke or rotate token)."""
        result = await self.session.execute(
            select(SessionModel).where(SessionModel.id == session.id),
        )
        model = result.scalar_one()
        model.refresh_token_hash = session.refresh_token_hash
        model.revoked_at = session.revoked_at
        model.previous_session_id = session.previous_session_id
        model.rotation_counter = session.rotation_counter
        await self.session.flush()
        return self._to_session_entity(model)

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
