"""Unit tests for UserService — fast, isolated, with mocked collaborators.

The repository, Unit of Work, and cache are mocked so these tests exercise
only the service's own branch logic (conflict detection, not-found guards,
privileged writes) without touching a database.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.core.cache import CacheClient
from src.db.unit_of_work import UnitOfWork
from src.modules.users.entities import User, UserRole, UserStatus
from src.modules.users.exceptions import (
    InvalidStatusTransitionError,
    UserAlreadyExistsError,
    UserAlreadyInactiveError,
    UserNotFoundError,
)
from src.modules.users.repository import UserRepository
from src.modules.users.schemas import UserCreate, UserUpdate
from src.modules.users.service import UserService


def _make_user(**overrides: object) -> User:
    """Build a User entity with sensible defaults for tests."""
    defaults: dict[str, object] = {
        "user_id": "user-1",
        "email": "alice@example.com",
        "username": "alice",
        "hashed_password": "hashed",
        "status": UserStatus.ACTIVE,
        "role": UserRole.USER,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return User(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def repo() -> AsyncMock:
    """Return a mocked UserRepository."""
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def uow() -> AsyncMock:
    """Return a mocked Unit of Work."""
    return AsyncMock(spec=UnitOfWork)


@pytest.fixture
def cache() -> AsyncMock:
    """Return a mocked cache client."""
    return AsyncMock(spec=CacheClient)


@pytest.fixture
def service(repo: AsyncMock, uow: AsyncMock, cache: AsyncMock) -> UserService:
    """UserService wired with mocked collaborators."""
    return UserService(repository=repo, uow=uow, cache=cache)


# ── create_user ───────────────────────────────────────────


async def test_create_user_success(service: UserService, repo: AsyncMock, uow: AsyncMock) -> None:
    """Creating a non-conflicting user persists and commits."""
    repo.get_by_email_or_username.return_value = None
    created = _make_user()
    repo.create.return_value = created

    payload = UserCreate(email="alice@example.com", username="alice", password="securepass123")
    result = await service.create_user(payload)

    assert result is created
    repo.create.assert_awaited_once()
    uow.commit.assert_awaited_once()


async def test_create_user_duplicate_email(service: UserService, repo: AsyncMock) -> None:
    """A conflicting email raises UserAlreadyExistsError and never commits."""
    repo.get_by_email_or_username.return_value = _make_user(email="alice@example.com")

    payload = UserCreate(email="alice@example.com", username="different", password="securepass123")
    with pytest.raises(UserAlreadyExistsError, match="email"):
        await service.create_user(payload)


async def test_create_user_duplicate_username(service: UserService, repo: AsyncMock) -> None:
    """A conflicting username (different email) raises UserAlreadyExistsError."""
    repo.get_by_email_or_username.return_value = _make_user(
        email="other@example.com", username="alice"
    )

    payload = UserCreate(email="new@example.com", username="alice", password="securepass123")
    with pytest.raises(UserAlreadyExistsError, match="username"):
        await service.create_user(payload)


# ── get_user ──────────────────────────────────────────────


async def test_get_user_not_found(service: UserService, repo: AsyncMock) -> None:
    """get_user raises UserNotFoundError when the id is unknown."""
    repo.get_by_id.return_value = None
    with pytest.raises(UserNotFoundError):
        await service.get_user("missing")


# ── update_user ───────────────────────────────────────────


async def test_update_user_not_found(service: UserService, repo: AsyncMock) -> None:
    """Updating a missing user raises UserNotFoundError."""
    repo.get_by_id.return_value = None
    with pytest.raises(UserNotFoundError):
        await service.update_user("missing", UserUpdate(username="newname"))


async def test_update_user_email_conflict(service: UserService, repo: AsyncMock) -> None:
    """Updating to an email owned by another user raises UserAlreadyExistsError."""
    repo.get_by_id.return_value = _make_user(user_id="user-1")
    repo.get_by_email.return_value = _make_user(user_id="user-2", email="taken@example.com")

    with pytest.raises(UserAlreadyExistsError):
        await service.update_user("user-1", UserUpdate(email="taken@example.com"))


async def test_update_user_success_commits_and_invalidates_cache(
    service: UserService, repo: AsyncMock, uow: AsyncMock, cache: AsyncMock
) -> None:
    """A valid update persists, commits, and invalidates the user cache."""
    existing = _make_user(user_id="user-1")
    repo.get_by_id.return_value = existing
    repo.get_by_username.return_value = None
    repo.update.return_value = _make_user(user_id="user-1", username="renamed")

    result = await service.update_user("user-1", UserUpdate(username="renamed"))

    assert result.username == "renamed"
    repo.update.assert_awaited_once()
    uow.commit.assert_awaited_once()
    cache.delete.assert_awaited_once_with("user:user-1")


async def test_update_user_no_fields_skips_commit(
    service: UserService, repo: AsyncMock, uow: AsyncMock
) -> None:
    """An empty update neither writes nor commits."""
    repo.get_by_id.return_value = _make_user(user_id="user-1")

    await service.update_user("user-1", UserUpdate())

    repo.update.assert_not_called()
    uow.commit.assert_not_called()


# ── set_password (privileged) ─────────────────────────────


async def test_set_password_not_found(service: UserService, repo: AsyncMock) -> None:
    """Setting a password for a missing user raises UserNotFoundError."""
    repo.get_by_id.return_value = None
    with pytest.raises(UserNotFoundError):
        await service.set_password("missing", "newsecret123")


async def test_set_password_hashes_and_persists(
    service: UserService, repo: AsyncMock, uow: AsyncMock, cache: AsyncMock
) -> None:
    """set_password stores a hash (never the plaintext) and commits."""
    repo.get_by_id.return_value = _make_user(user_id="user-1")
    repo.set_credentials.return_value = _make_user(user_id="user-1")

    await service.set_password("user-1", "newsecret123")

    repo.set_credentials.assert_awaited_once()
    _, kwargs = repo.set_credentials.call_args
    assert kwargs["hashed_password"] != "newsecret123"
    uow.commit.assert_awaited_once()
    cache.delete.assert_awaited_once_with("user:user-1")


# ── change_status (privileged) ────────────────────────────


async def test_change_status_invalid_transition(service: UserService, repo: AsyncMock) -> None:
    """An illegal state-machine transition raises InvalidStatusTransitionError."""
    repo.get_by_id.return_value = _make_user(status=UserStatus.ACTIVE)
    # ACTIVE -> PENDING_VERIFICATION is not allowed.
    with pytest.raises(InvalidStatusTransitionError):
        await service.change_status("user-1", UserStatus.PENDING_VERIFICATION)


async def test_change_status_valid_transition_commits(
    service: UserService, repo: AsyncMock, uow: AsyncMock
) -> None:
    """A legal transition persists the new status and commits."""
    repo.get_by_id.return_value = _make_user(status=UserStatus.ACTIVE)
    repo.set_status.return_value = _make_user(status=UserStatus.SUSPENDED)

    result = await service.change_status("user-1", UserStatus.SUSPENDED)

    assert result.status == UserStatus.SUSPENDED
    repo.set_status.assert_awaited_once()
    uow.commit.assert_awaited_once()


# ── delete_user (soft delete) ─────────────────────────────


async def test_delete_user_not_found(service: UserService, repo: AsyncMock) -> None:
    """Deleting a missing user raises UserNotFoundError."""
    repo.get_by_id.return_value = None
    with pytest.raises(UserNotFoundError):
        await service.delete_user("missing")


async def test_delete_user_already_inactive(service: UserService, repo: AsyncMock) -> None:
    """Deleting an already soft-deleted user raises UserAlreadyInactiveError."""
    repo.get_by_id.return_value = _make_user(deleted_at=datetime.now(UTC))
    with pytest.raises(UserAlreadyInactiveError):
        await service.delete_user("user-1")


async def test_delete_user_soft_deletes_and_commits(
    service: UserService, repo: AsyncMock, uow: AsyncMock, cache: AsyncMock
) -> None:
    """Deleting an active user sets deleted_at, commits, and clears the cache."""
    repo.get_by_id.return_value = _make_user(user_id="user-1", deleted_at=None)

    await service.delete_user("user-1")

    repo.update.assert_awaited_once()
    _, kwargs = repo.update.call_args
    assert kwargs["deleted_at"] is not None
    uow.commit.assert_awaited_once()
    cache.delete.assert_awaited_once_with("user:user-1")
