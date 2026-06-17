"""User domain entity — business behaviour separate from persistence.

Domain entities carry business methods and enforce invariants.
They are plain Python objects — no framework imports allowed.
"""

from datetime import datetime


class User:
    """User domain entity — the source of truth for business rules."""

    def __init__(
        self,
        user_id: str,
        email: str,
        username: str,
        hashed_password: str,
        is_active: bool = True,
        is_superuser: bool = False,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.id = user_id
        self.email = email
        self.username = username
        self.hashed_password = hashed_password
        self.is_active = is_active
        self.is_superuser = is_superuser
        self.created_at = created_at
        self.updated_at = updated_at

    # ── Business methods ──────────────────────────────────

    def deactivate(self) -> None:
        """Deactivate the user account."""
        self.is_active = False

    def activate(self) -> None:
        """Activate the user account."""
        self.is_active = True

    def change_password(self, new_hashed_password: str) -> None:
        """Update the stored password hash."""
        self.hashed_password = new_hashed_password

    def promote(self) -> None:
        """Grant superuser privileges."""
        self.is_superuser = True

    def demote(self) -> None:
        """Revoke superuser privileges."""
        self.is_superuser = False
