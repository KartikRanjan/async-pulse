"""User service — use-case logic, framework-agnostic.

Depends on the repository for data access and the Unit of Work for
transaction boundaries.  Never imports FastAPI, requests, or responses.
"""

import uuid
from typing import Any

from src.core.cache import CacheClient
from src.db.unit_of_work import UnitOfWork
from src.modules.users.entities import User, UserStatus
from src.modules.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from src.modules.users.repository import UserRepository
from src.modules.users.schemas import UserCreate, UserUpdate
from src.shared.security import hash_password


class UserService:
    """Orchestrates user-related business operations."""

    def __init__(
        self,
        repository: UserRepository,
        uow: UnitOfWork,
        cache: CacheClient | None = None,
    ) -> None:
        self.repo = repository
        self.uow = uow
        self.cache = cache

    # ── Queries (for cross-module consumption) ────────────

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email. Returns ``None`` if not found."""
        return await self.repo.get_by_email(email)

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Fetch a user by ID. Returns ``None`` if not found."""
        return await self.repo.get_by_id(user_id)

    # ── Commands ──────────────────────────────────────────

    async def create_user(self, payload: UserCreate) -> User:
        """Register a new user. Raises ``UserAlreadyExistsError`` on conflict."""
        existing = await self.repo.get_by_email_or_username(payload.email, payload.username)
        if existing:
            if existing.email == payload.email:
                raise UserAlreadyExistsError("A user with this email already exists")
            raise UserAlreadyExistsError("A user with this username already exists")

        # Initial status is PENDING_VERIFICATION for new users, role is USER
        user = await self.repo.create(
            user_id=str(uuid.uuid4()),
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(payload.password),
        )
        await self.uow.commit()
        return user

    async def get_user(self, user_id: str) -> User:
        """Fetch a user by ID. Raises ``UserNotFoundError`` if missing."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        return user

    async def list_users(self, offset: int, limit: int) -> tuple[list[User], int]:
        """Return a paginated list of users and total count."""
        return await self.repo.list_users(offset, limit)

    async def update_user(
        self,
        user_id: str,
        payload: UserUpdate,
        *,
        current_user_id: str | None = None,
    ) -> User:
        """Update a user's profile fields. Raises ``UserNotFoundError`` if missing."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)

        update_fields: dict[str, Any] = {}
        if payload.email is not None:
            existing = await self.repo.get_by_email(payload.email)
            if existing and existing.id != user_id:
                raise UserAlreadyExistsError("A user with this email already exists")
            update_fields["email"] = payload.email
        if payload.username is not None:
            existing = await self.repo.get_by_username(payload.username)
            if existing and existing.id != user_id:
                raise UserAlreadyExistsError("A user with this username already exists")
            update_fields["username"] = payload.username

        if update_fields:
            user = await self.repo.update(user, **update_fields)
            await self.uow.commit()
            if self.cache:
                await self.cache.delete(f"user:{user_id}")

        return user

    # ── Privileged commands (credential / status) ─────────
    #
    # The users module owns the ``users`` table, so all writes to the
    # security-sensitive columns flow through here. Other modules (e.g. auth)
    # call these via the public ``UserService`` API instead of reaching into
    # the users persistence model directly.

    async def set_password(self, user_id: str, new_password: str) -> User:
        """Set a new password hash for a user. Raises ``UserNotFoundError`` if missing."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        updated = await self.repo.set_credentials(
            user_id,
            hashed_password=hash_password(new_password),
        )
        await self.uow.commit()
        if self.cache:
            await self.cache.delete(f"user:{user_id}")
        return updated

    async def change_status(self, user_id: str, new_status: UserStatus) -> User:
        """Transition a user's lifecycle status, enforcing entity state-machine rules.

        Raises ``UserNotFoundError`` if missing and ``InvalidStatusTransitionError``
        if the transition is not allowed.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        user.transition_to(new_status)
        updated = await self.repo.set_status(user_id, status=user.status)
        await self.uow.commit()
        if self.cache:
            await self.cache.delete(f"user:{user_id}")
        return updated

    async def delete_user(self, user_id: str) -> None:
        """Soft-delete a user. Raises ``UserNotFoundError`` if missing."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        user.deactivate()
        await self.repo.update(user, deleted_at=user.deleted_at)
        await self.uow.commit()
        if self.cache:
            await self.cache.delete(f"user:{user_id}")
