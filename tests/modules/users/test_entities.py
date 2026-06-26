"""Unit tests for the User domain entity — pure, no I/O.

These cover the business invariants the entity is responsible for:
soft-delete guarding, the status state machine, and role helpers.
"""

import pytest

from src.modules.users.entities import User, UserRole, UserStatus
from src.modules.users.exceptions import (
    InvalidStatusTransitionError,
    UserAlreadyInactiveError,
)


def _make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "user_id": "user-1",
        "email": "alice@example.com",
        "username": "alice",
        "hashed_password": "hashed",
    }
    defaults.update(overrides)
    return User(**defaults)  # type: ignore[arg-type]


# ── deactivate / activate ─────────────────────────────────


def test_deactivate_sets_deleted_at() -> None:
    """Deactivate marks the user soft-deleted."""
    user = _make_user()
    assert user.deleted_at is None
    user.deactivate()
    assert user.deleted_at is not None


def test_deactivate_twice_raises() -> None:
    """Deactivating an already-inactive user raises."""
    user = _make_user()
    user.deactivate()
    with pytest.raises(UserAlreadyInactiveError):
        user.deactivate()


def test_activate_restores_user() -> None:
    """Activate clears the soft-delete marker."""
    user = _make_user()
    user.deactivate()
    user.activate()
    assert user.deleted_at is None


# ── status state machine ──────────────────────────────────


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (UserStatus.PENDING_VERIFICATION, UserStatus.ACTIVE),
        (UserStatus.PENDING_VERIFICATION, UserStatus.BANNED),
        (UserStatus.ACTIVE, UserStatus.SUSPENDED),
        (UserStatus.ACTIVE, UserStatus.BANNED),
        (UserStatus.SUSPENDED, UserStatus.ACTIVE),
        (UserStatus.SUSPENDED, UserStatus.BANNED),
    ],
)
def test_valid_status_transitions(start: UserStatus, target: UserStatus) -> None:
    """Allowed transitions update the status."""
    user = _make_user(status=start)
    user.transition_to(target)
    assert user.status == target


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (UserStatus.BANNED, UserStatus.ACTIVE),
        (UserStatus.BANNED, UserStatus.SUSPENDED),
        (UserStatus.ACTIVE, UserStatus.PENDING_VERIFICATION),
        (UserStatus.SUSPENDED, UserStatus.PENDING_VERIFICATION),
    ],
)
def test_invalid_status_transitions(start: UserStatus, target: UserStatus) -> None:
    """Disallowed transitions raise InvalidStatusTransitionError."""
    user = _make_user(status=start)
    with pytest.raises(InvalidStatusTransitionError):
        user.transition_to(target)


def test_transition_to_same_status_is_noop() -> None:
    """Transitioning to the current status is a no-op, not an error."""
    user = _make_user(status=UserStatus.ACTIVE)
    user.transition_to(UserStatus.ACTIVE)
    assert user.status == UserStatus.ACTIVE


# ── role helpers ──────────────────────────────────────────


def test_role_promotion_and_demotion() -> None:
    """Role helpers move the user between roles."""
    user = _make_user(role=UserRole.USER)
    assert user.is_superuser is False

    user.promote_to_admin()
    assert user.role == UserRole.ADMIN

    user.promote_to_superuser()
    assert user.role == UserRole.SUPERUSER
    assert user.is_superuser is True

    user.demote_to_user()
    assert user.role == UserRole.USER


def test_is_fully_active_requires_active_status_and_not_deleted() -> None:
    """is_fully_active is only true for an ACTIVE, non-deleted user."""
    assert _make_user(status=UserStatus.ACTIVE).is_fully_active is True
    assert _make_user(status=UserStatus.SUSPENDED).is_fully_active is False

    deleted = _make_user(status=UserStatus.ACTIVE)
    deleted.deactivate()
    assert deleted.is_fully_active is False
