"""Password hashing and JWT token utilities.

All cryptographic helpers live here as module-level singletons — never
constructor-injected (see CODING_CONVENTIONS §16).

Uses bcrypt directly — never passlib (passlib is incompatible with bcrypt>=4.1).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import jwt

from src.core.settings import get_settings

# ── Password helpers ─────────────────────────────────────


def hash_password(password: str) -> str:
    """Return the bcrypt hash of *password*."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check *plain_password* against a bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ── JWT helpers ───────────────────────────────────────────


def create_access_token(subject: str, session_id: str | None = None) -> str:
    """Create a short-lived access token for *subject* (user id)."""
    settings = get_settings()
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(subject, expires, token_type="access", session_id=session_id)


def create_refresh_token(subject: str, session_id: str, expires_in: int | None = None) -> str:
    """Create a long-lived refresh token with a session ID (jti) for RTR.

    Args:
        subject: The user ID to embed as ``sub``.
        session_id: The session UUID to embed as ``jti``.
        expires_in: Optional TTL in seconds. When provided (e.g. during token
            rotation), the JWT expiry is capped to the remaining chain lifetime
            instead of stamping a fresh full-length expiry. When omitted (e.g.
            at initial login), falls back to ``REFRESH_TOKEN_EXPIRE_DAYS``.
    """
    settings = get_settings()
    if expires_in is not None:
        expires = timedelta(seconds=expires_in)
    else:
        expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(subject, expires, token_type="refresh", session_id=session_id)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.

    Returns the payload dict on success.
    Raises ``jose.JWTError`` on any validation failure.
    """
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return payload


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: str,
    session_id: str | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": token_type}
    if session_id:
        if token_type == "refresh":
            payload["jti"] = session_id
        else:
            payload["sid"] = session_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
