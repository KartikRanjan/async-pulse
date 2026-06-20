"""Auth domain entities — business rules for authentication and sessions.

These are plain Python objects separate from database persistence.
"""

from datetime import UTC, datetime
from typing import Self, cast

from src.modules.users.entities import UserRole, UserStatus


class AuthIdentity:
    """Represents a security/credential identity for a user.

    Used by the Auth module to validate credentials, status, and role privileges
    independently from full profile details.
    """

    def __init__(
        self,
        user_id: str,
        email: str,
        username: str,
        hashed_password: str,
        status: UserStatus,
        role: UserRole,
        deleted_at: datetime | None = None,
    ) -> None:
        self.id = user_id
        self.email = email
        self.username = username
        self.hashed_password = hashed_password
        self.status = status
        self.role = role
        self.deleted_at = deleted_at

    @property
    def is_active(self) -> bool:
        """Verify if the identity is active and verified."""
        return self.status == UserStatus.ACTIVE and self.deleted_at is None

    @property
    def is_suspended(self) -> bool:
        """Check if account is temporarily suspended."""
        return self.status == UserStatus.SUSPENDED

    @property
    def is_banned(self) -> bool:
        """Check if account is banned."""
        return self.status == UserStatus.BANNED

    @property
    def is_verified(self) -> bool:
        """Check if email verification is complete."""
        return self.status != UserStatus.PENDING_VERIFICATION


class UserSession:
    """Represents an active Refresh Token Rotation (RTR) session."""

    def __init__(
        self,
        session_id: str,
        user_id: str,
        refresh_token_hash: str,
        expires_at: datetime,
        device_info: str | None = None,
        ip_address: str | None = None,
        created_at: datetime | None = None,
        revoked_at: datetime | None = None,
        previous_session_id: str | None = None,
        rotation_counter: int = 0,
    ) -> None:
        self.id = session_id
        self.user_id = user_id
        self.refresh_token_hash = refresh_token_hash
        self.expires_at = expires_at
        self.device_info = device_info
        self.ip_address = ip_address
        self.created_at = created_at or datetime.now(UTC)
        self.revoked_at = revoked_at
        self.previous_session_id = previous_session_id
        self.rotation_counter = rotation_counter

    @property
    def is_expired(self) -> bool:
        """Check if the session has expired."""
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if the session has been revoked."""
        return self.revoked_at is not None

    @property
    def is_active(self) -> bool:
        """Check if the session is currently valid and active."""
        return not self.is_expired and not self.is_revoked

    def revoke(self) -> None:
        """Revoke the current session."""
        if not self.revoked_at:
            self.revoked_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, object]:
        """Serialize session state for caching."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "refresh_token_hash": self.refresh_token_hash,
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "previous_session_id": self.previous_session_id,
            "rotation_counter": self.rotation_counter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        """Deserialize session state from cache dict."""
        return cls(
            session_id=str(data["id"]),
            user_id=str(data["user_id"]),
            refresh_token_hash=str(data["refresh_token_hash"]),
            expires_at=datetime.fromisoformat(str(data["expires_at"])),
            device_info=str(data["device_info"]) if data.get("device_info") else None,
            ip_address=str(data["ip_address"]) if data.get("ip_address") else None,
            created_at=datetime.fromisoformat(str(data["created_at"])),
            revoked_at=datetime.fromisoformat(str(data["revoked_at"]))
            if data.get("revoked_at")
            else None,
            previous_session_id=str(data["previous_session_id"])
            if data.get("previous_session_id")
            else None,
            rotation_counter=int(cast("int", data.get("rotation_counter", 0))),
        )
