"""Auth domain entities — business rules for authentication and sessions.

These are plain Python objects separate from database persistence.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Self


@dataclass(frozen=True)
class SessionValidation:
    """Minimal cache projection for the auth gate hot path.

    This is the *only* type written to and read from ``session:{id}`` in Redis.
    It carries exactly the four fields the gate needs:

    - ``id`` / ``user_id`` — ownership check (``session.user_id == token.sub``)
    - ``expires_at`` — expiry check
    - ``revoked_at`` — revocation check (null = active)

    Forensic/UI metadata (``device_info``, ``ip_address``, ``created_at``,
    ``previous_session_id``) is never cached — it lives in the DB and is only
    read by write-side paths (rotation) or UI queries (list sessions), both of
    which go to the source of truth directly.
    """

    id: str
    user_id: str
    expires_at: datetime
    revoked_at: datetime | None

    # ── Business properties ───────────────────────────────

    @property
    def is_expired(self) -> bool:
        """Return True if the session has passed its hard expiry."""
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at

    @property
    def is_revoked(self) -> bool:
        """Return True if the session has been explicitly revoked."""
        return self.revoked_at is not None

    @property
    def is_active(self) -> bool:
        """Return True if the session is neither expired nor revoked."""
        return not self.is_expired and not self.is_revoked

    # ── Cache serialization ───────────────────────────────

    def to_dict(self) -> dict[str, object]:
        """Serialize to the ``session:{id}`` Redis payload."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "expires_at": self.expires_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        """Deserialize from the ``session:{id}`` Redis payload."""
        return cls(
            id=str(data["id"]),
            user_id=str(data["user_id"]),
            expires_at=datetime.fromisoformat(str(data["expires_at"])),
            revoked_at=datetime.fromisoformat(str(data["revoked_at"]))
            if data.get("revoked_at")
            else None,
        )

    @classmethod
    def from_session(cls, session: "UserSession") -> Self:
        """Project a full ``UserSession`` domain entity into this validation view."""
        return cls(
            id=session.id,
            user_id=session.user_id,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
        )


class UserSession:
    """Full session domain entity — the authoritative write-side representation.

    Returned by the repository from DB reads. Used by:
    - ``AuthService.authenticate`` (create session)
    - ``AuthService.refresh_token`` (rotation — needs device_info, chain metadata)
    - ``AuthService.logout`` / ``logout_all`` (revoke)
    - ``GET /auth/sessions`` (device management listing)

    Never reconstructed from cache. The cache projection is ``SessionValidation``.
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        expires_at: datetime,
        device_info: str | None = None,
        ip_address: str | None = None,
        created_at: datetime | None = None,
        revoked_at: datetime | None = None,
        previous_session_id: str | None = None,
    ) -> None:
        self.id = session_id
        self.user_id = user_id
        self.expires_at = expires_at
        self.device_info = device_info
        self.ip_address = ip_address
        self.created_at = created_at or datetime.now(UTC)
        self.revoked_at = revoked_at
        self.previous_session_id = previous_session_id

    @property
    def is_expired(self) -> bool:
        """Return True if the session has passed its hard expiry."""
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at

    @property
    def is_revoked(self) -> bool:
        """Return True if the session has been explicitly revoked."""
        return self.revoked_at is not None

    @property
    def is_active(self) -> bool:
        """Return True if the session is neither expired nor revoked."""
        return not self.is_expired and not self.is_revoked

    def revoke(self) -> None:
        """Mark this session as revoked at the current UTC time."""
        if not self.revoked_at:
            self.revoked_at = datetime.now(UTC)
