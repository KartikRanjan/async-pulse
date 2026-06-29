"""User repository — data access only, no business logic.

Handles SQLAlchemy queries and maps between persistence models
(``UserModel``) and domain entities (``User``).
Never commits — transaction boundaries are managed by the Unit of Work.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.entities import User, UserStatus
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
            name=model.name,
            username=model.username,
            hashed_password=model.hashed_password,
            status=model.status,
            role=model.role,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # ── Reads ─────────────────────────────────────────────

    async def get_by_id(self, user_id: str) -> User | None:
        """Fetch a user by primary key if not soft-deleted."""
        result = await self.session.execute(
            select(UserModel).where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
            ),
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address if not soft-deleted."""
        result = await self.session.execute(
            select(UserModel).where(
                UserModel.email == email,
                UserModel.deleted_at.is_(None),
            ),
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_username(self, username: str) -> User | None:
        """Fetch a user by username if not soft-deleted."""
        result = await self.session.execute(
            select(UserModel).where(
                UserModel.username == username,
                UserModel.deleted_at.is_(None),
            ),
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_email_or_username(self, email: str, username: str) -> User | None:
        """Check if a user exists with the given email *or* username (single query)."""
        result = await self.session.execute(
            select(UserModel).where(
                or_(UserModel.email == email, UserModel.username == username),
                UserModel.deleted_at.is_(None),
            ),
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_users(self, offset: int, limit: int) -> tuple[list[User], int]:
        """Return a paginated list of active users and the total count."""
        count_result = await self.session.execute(
            select(func.count()).select_from(UserModel).where(UserModel.deleted_at.is_(None))
        )
        total = count_result.scalar_one()

        result = await self.session.execute(
            select(UserModel)
            .where(UserModel.deleted_at.is_(None))
            .order_by(UserModel.created_at.desc())
            .offset(offset)
            .limit(limit),
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models], total

    # ── Writes ────────────────────────────────────────────

    async def create(
        self,
        *,
        user_id: str,
        email: str,
        name: str,
        username: str,
        hashed_password: str,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        """Persist a new user and return the domain entity."""
        model = UserModel(
            id=user_id,
            email=email,
            name=name,
            username=username,
            hashed_password=hashed_password,
            status=status,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_entity(model)

    async def update(self, user: User, **fields: object) -> User:
        """Update a user's profile fields. Enforces field privilege separation."""
        forbidden = {"hashed_password", "status", "role"}
        if any(f in fields for f in forbidden):
            raise TypeError("UserRepository cannot modify security, credential, or status fields")

        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user.id),
        )
        model = result.scalar_one()
        for key, value in fields.items():
            setattr(model, key, value)
        model.updated_at = datetime.now(UTC)
        await self.session.flush()
        return self._to_entity(model)

    # ── Privileged Writes (credential / status) ───────────
    #
    # These are the single owner of the security-sensitive columns on the
    # ``users`` table. They are intentionally separate from ``update`` (which
    # forbids these fields) so that profile updates can never touch credentials
    # or status. Cross-module callers (e.g. the auth module) reach these only
    # through ``UserService``, never the repository directly.

    async def set_credentials(self, user_id: str, *, hashed_password: str) -> User:
        """Update a user's password hash. Privileged credential operation."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id),
        )
        model = result.scalar_one()
        model.hashed_password = hashed_password
        model.updated_at = datetime.now(UTC)
        await self.session.flush()
        return self._to_entity(model)

    async def set_status(self, user_id: str, *, status: UserStatus) -> User:
        """Update a user's lifecycle status. Privileged operation."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id),
        )
        model = result.scalar_one()
        model.status = status
        model.updated_at = datetime.now(UTC)
        await self.session.flush()
        return self._to_entity(model)

    async def delete(self, user_id: str) -> None:
        """Perform a hard delete of the user model (admin functionality)."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id),
        )
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()
