"""User repository — data access only, no business logic.

Handles SQLAlchemy queries and maps between persistence models
(``UserModel``) and domain entities (``User``).
Never commits — transaction boundaries are managed by the Unit of Work.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.entities import User
from src.modules.users.models import UserModel


class UserRepository:
    """Data access layer for the User aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Mapping ───────────────────────────────────────────

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        """Map a persistence model to a domain entity."""
        return User(
            user_id=model.id,
            email=model.email,
            username=model.username,
            hashed_password=model.hashed_password,
            is_active=model.is_active,
            is_superuser=model.is_superuser,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # ── Reads ─────────────────────────────────────────────

    async def get_by_id(self, user_id: str) -> User | None:
        """Fetch a user by primary key."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id),
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email),
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_username(self, username: str) -> User | None:
        """Fetch a user by username."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.username == username),
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_users(self, offset: int, limit: int) -> tuple[list[User], int]:
        """Return a paginated list of users and the total count."""
        count_result = await self.session.execute(select(func.count()).select_from(UserModel))
        total = count_result.scalar_one()

        result = await self.session.execute(
            select(UserModel).order_by(UserModel.created_at.desc()).offset(offset).limit(limit),
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models], total

    # ── Writes ────────────────────────────────────────────

    async def create(
        self,
        *,
        email: str,
        username: str,
        hashed_password: str,
    ) -> User:
        """Persist a new user and return the domain entity."""
        model = UserModel(
            id=str(uuid.uuid4()),
            email=email,
            username=username,
            hashed_password=hashed_password,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_entity(model)

    async def update(self, user: User, **fields: object) -> User:
        """Update a user's fields and return the refreshed domain entity."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user.id),
        )
        model = result.scalar_one()
        for key, value in fields.items():
            setattr(model, key, value)
        model.updated_at = datetime.now(UTC)
        await self.session.flush()
        return self._to_entity(model)

    async def delete(self, user_id: str) -> None:
        """Soft-delete is preferred — this performs a hard delete."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id),
        )
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()
