"""User domain entity — business behaviour separate from persistence.

Domain entities carry business methods and enforce invariants.
They are plain Python objects — no framework imports allowed.
"""

from datetime import UTC, datetime
from enum import StrEnum

from src.modules.users.exceptions import InvalidStatusTransitionError, UserAlreadyInactiveError


class UserStatus(StrEnum):
    """Possible authentication and lifecycle states of a user."""

    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"


class UserRole(StrEnum):
    """Authorization roles within the application."""

    USER = "user"
    ADMIN = "admin"
    SUPERUSER = "superuser"


class User:
    """User domain entity — the source of truth for business rules."""

    def __init__(
        self,
        user_id: str,
        email: str,
        username: str,
        hashed_password: str,
        status: UserStatus = UserStatus.ACTIVE,
        role: UserRole = UserRole.USER,
        deleted_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.id = user_id
        self.email = email
        self.username = username
        self.hashed_password = hashed_password
        self.status = status
        self.role = role
        self.deleted_at = deleted_at
        self.created_at = created_at
        self.updated_at = updated_at

    # ── Business methods ──────────────────────────────────

    def transition_to(self, new_status: UserStatus) -> None:
        """Transition the user status following strict state machine rules."""
        valid_transitions = {
            UserStatus.PENDING_VERIFICATION: {UserStatus.ACTIVE, UserStatus.BANNED},
            UserStatus.ACTIVE: {UserStatus.SUSPENDED, UserStatus.BANNED},
            UserStatus.SUSPENDED: {UserStatus.ACTIVE, UserStatus.BANNED},
            UserStatus.BANNED: set[UserStatus](),
        }
        if new_status == self.status:
            return
        allowed = valid_transitions.get(self.status, set[UserStatus]())
        if new_status not in allowed:
            raise InvalidStatusTransitionError(self.id, self.status, new_status)
        self.status = new_status

    def deactivate(self) -> None:
        """Soft-delete/deactivate the user profile."""
        if self.deleted_at is not None:
            raise UserAlreadyInactiveError(self.id)
        self.deleted_at = datetime.now(UTC)

    def activate(self) -> None:
        """Restore a soft-deleted user profile."""
        self.deleted_at = None

    def change_password(self, new_hashed_password: str) -> None:
        """Update the stored password hash."""
        self.hashed_password = new_hashed_password

    def promote_to_admin(self) -> None:
        """Promote the user to admin role."""
        self.role = UserRole.ADMIN

    def promote_to_superuser(self) -> None:
        """Promote the user to superuser role."""
        self.role = UserRole.SUPERUSER

    def demote_to_user(self) -> None:
        """Demote the user to standard role."""
        self.role = UserRole.USER

    @property
    def is_active(self) -> bool:
        """Helper to check if user profile is not soft-deleted and status is active."""
        return self.deleted_at is None and self.status == UserStatus.ACTIVE

    @property
    def is_superuser(self) -> bool:
        """Helper to check if user has superuser privileges."""
        return self.role == UserRole.SUPERUSER
