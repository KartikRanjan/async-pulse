"""User service — use-case logic, framework-agnostic.

Depends on the repository for data access and the Unit of Work for
transaction boundaries.  Never imports FastAPI, requests, or responses.
"""

from typing import Any

from src.db.unit_of_work import UnitOfWork
from src.modules.users.entities import User
from src.modules.users.exceptions import (
    UserAlreadyExistsError,
    UserDeactivationError,
    UserNotFoundError,
)
from src.modules.users.repository import UserRepository
from src.modules.users.schemas import UserCreate, UserUpdate
from src.shared.security import hash_password


class UserService:
    """Orchestrates user-related business operations."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    @property
    def repo(self) -> UserRepository:
        """Shortcut to the user repository on the current UoW."""
        if self.uow.users is None:
            raise RuntimeError("UserService.repo accessed before UnitOfWork was entered")
        return self.uow.users

    # ── Commands ──────────────────────────────────────────

    async def create_user(self, payload: UserCreate) -> User:
        """Register a new user. Raises ``UserAlreadyExistsError`` on conflict."""
        existing = await self.repo.get_by_email_or_username(payload.email, payload.username)
        if existing:
            if existing.email == payload.email:
                raise UserAlreadyExistsError("A user with this email already exists")
            raise UserAlreadyExistsError("A user with this username already exists")

        user = await self.repo.create(
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
        """Update a user's fields. Raises ``UserNotFoundError`` if missing."""
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
        if payload.password is not None:
            update_fields["hashed_password"] = hash_password(payload.password)
        if payload.is_active is not None:
            if current_user_id and user_id == current_user_id and not payload.is_active:
                raise UserDeactivationError()
            update_fields["is_active"] = payload.is_active

        if update_fields:
            user = await self.repo.update(user, **update_fields)
            await self.uow.commit()

        return user

    async def delete_user(self, user_id: str) -> None:
        """Delete a user. Raises ``UserNotFoundError`` if missing."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        await self.repo.delete(user_id)
        await self.uow.commit()
