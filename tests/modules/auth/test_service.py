"""Unit tests for AuthService — mocked collaborators, no database.

Covers the credential/status guard branches of ``authenticate``, the
token-validation branches of ``refresh_token``, and session revocation on
logout. RTR rotation, breach detection, and grace-period behaviour are
covered end-to-end in ``test_rtr_and_rbac.py``.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.core.cache import CacheClient
from src.db.unit_of_work import UnitOfWork
from src.modules.auth.entities import UserSession
from src.modules.auth.exceptions import InvalidCredentialsError, InvalidTokenError
from src.modules.auth.repository import AuthRepository
from src.modules.auth.service import AuthService, AuthServiceDeps
from src.modules.users.entities import User, UserRole, UserStatus
from src.modules.users.exceptions import UserBannedError, UserSuspendedError
from src.modules.users.service import UserService
from src.shared.security import create_access_token, create_refresh_token, hash_password

PLAIN_PASSWORD = "securepass123"


def _make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "user_id": "user-1",
        "email": "alice@example.com",
        "username": "alice",
        "hashed_password": hash_password(PLAIN_PASSWORD),
        "status": UserStatus.ACTIVE,
        "role": UserRole.USER,
    }
    defaults.update(overrides)
    return User(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def repo() -> AsyncMock:
    """Return a mocked AuthRepository."""
    return AsyncMock(spec=AuthRepository)


@pytest.fixture
def users() -> AsyncMock:
    """Return a mocked UserService."""
    return AsyncMock(spec=UserService)


@pytest.fixture
def uow() -> AsyncMock:
    """Return a mocked Unit of Work."""
    return AsyncMock(spec=UnitOfWork)


@pytest.fixture
def cache() -> AsyncMock:
    """Return a mocked cache client."""
    return AsyncMock(spec=CacheClient)


@pytest.fixture
def service(repo: AsyncMock, users: AsyncMock, uow: AsyncMock, cache: AsyncMock) -> AuthService:
    """Return an AuthService wired with mocked collaborators."""
    return AuthService(
        deps=AuthServiceDeps(repository=repo, user_service=users, uow=uow, cache=cache)
    )


# ── authenticate ──────────────────────────────────────────


async def test_authenticate_unknown_email(service: AuthService, users: AsyncMock) -> None:
    """No matching user raises InvalidCredentialsError."""
    users.get_user_by_email.return_value = None
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate("ghost@example.com", PLAIN_PASSWORD)


async def test_authenticate_wrong_password(service: AuthService, users: AsyncMock) -> None:
    """A bad password raises InvalidCredentialsError."""
    users.get_user_by_email.return_value = _make_user()
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate("alice@example.com", "wrong-password")


async def test_authenticate_suspended_user(service: AuthService, users: AsyncMock) -> None:
    """A suspended account cannot authenticate."""
    users.get_user_by_email.return_value = _make_user(status=UserStatus.SUSPENDED)
    with pytest.raises(UserSuspendedError):
        await service.authenticate("alice@example.com", PLAIN_PASSWORD)


async def test_authenticate_banned_user(service: AuthService, users: AsyncMock) -> None:
    """A banned account cannot authenticate."""
    users.get_user_by_email.return_value = _make_user(status=UserStatus.BANNED)
    with pytest.raises(UserBannedError):
        await service.authenticate("alice@example.com", PLAIN_PASSWORD)


async def test_authenticate_success_creates_session(
    service: AuthService, users: AsyncMock, repo: AsyncMock, uow: AsyncMock
) -> None:
    """Valid credentials create a session, commit, and return a token pair."""
    users.get_user_by_email.return_value = _make_user()
    repo.get_active_sessions_for_user.return_value = []

    tokens = await service.authenticate(
        "alice@example.com", PLAIN_PASSWORD, device_info="pytest", ip_address="127.0.0.1"
    )

    assert tokens.access_token
    assert tokens.refresh_token
    repo.create_session.assert_awaited_once()
    uow.commit.assert_awaited_once()


# ── refresh_token ─────────────────────────────────────────


async def test_refresh_token_garbage_token(service: AuthService) -> None:
    """A malformed refresh token raises InvalidTokenError."""
    from src.modules.auth.schemas import TokenRefreshRequest

    with pytest.raises(InvalidTokenError):
        await service.refresh_token(TokenRefreshRequest(refresh_token="not-a-jwt"))


async def test_refresh_token_wrong_type(service: AuthService) -> None:
    """Passing an access token to the refresh flow is rejected."""
    from src.modules.auth.schemas import TokenRefreshRequest

    access = create_access_token("user-1", "session-1")
    with pytest.raises(InvalidTokenError, match="not a refresh token"):
        await service.refresh_token(TokenRefreshRequest(refresh_token=access))


async def test_refresh_token_unknown_session(
    service: AuthService, repo: AsyncMock, cache: AsyncMock
) -> None:
    """A valid refresh token whose session no longer exists is rejected."""
    from src.modules.auth.schemas import TokenRefreshRequest

    refresh = create_refresh_token("user-1", "session-gone")
    cache.get_json.return_value = None
    repo.get_session_by_id.return_value = None

    with pytest.raises(InvalidTokenError, match="Session not found"):
        await service.refresh_token(TokenRefreshRequest(refresh_token=refresh))


# ── logout ────────────────────────────────────────────────


async def test_logout_revokes_existing_session(
    service: AuthService, repo: AsyncMock, uow: AsyncMock, cache: AsyncMock
) -> None:
    """Logout revokes the session, commits, and clears its cache entries."""
    session = UserSession(
        session_id="session-1",
        user_id="user-1",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo.get_session_by_id.return_value = session

    await service.logout("session-1")

    assert session.is_revoked
    repo.update_session.assert_awaited_once()
    uow.commit.assert_awaited_once()
    cache.delete.assert_any_await("session:session-1")


async def test_logout_missing_session_is_noop(
    service: AuthService, repo: AsyncMock, uow: AsyncMock
) -> None:
    """Logging out a non-existent session does nothing."""
    repo.get_session_by_id.return_value = None
    await service.logout("missing")
    uow.commit.assert_not_called()


async def test_logout_all_revokes_and_commits(
    service: AuthService, repo: AsyncMock, uow: AsyncMock
) -> None:
    """logout_all revokes every session for the user and commits once."""
    repo.get_active_sessions_for_user.return_value = []
    await service.logout_all("user-1")
    repo.revoke_all_sessions.assert_awaited_once_with("user-1")
    uow.commit.assert_awaited_once()
