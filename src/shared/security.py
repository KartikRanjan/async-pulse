"""Password hashing and JWT token utilities.

All cryptographic helpers live here as module-level singletons — never
constructor-injected (see CODING_CONVENTIONS §16).

Uses bcrypt directly — never passlib (passlib is incompatible with bcrypt>=4.1).
"""

from datetime import UTC, datetime, timedelta

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


def create_access_token(subject: str) -> str:
    """Create a short-lived access token for *subject* (user id)."""
    settings = get_settings()
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(subject, expires, token_type="access")  # noqa: S106


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token for *subject* (user id)."""
    settings = get_settings()
    expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(subject, expires, token_type="refresh")  # noqa: S106


def decode_token(token: str) -> dict:
    """Decode and validate a JWT.

    Returns the payload dict on success.
    Raises ``jose.JWTError`` on any validation failure.
    """
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": token_type}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
