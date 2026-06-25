"""Application settings — pydantic-settings with .env support.

Module-level singleton via ``@lru_cache`` (CODING_CONVENTIONS §16).
Never constructor-injected.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Pydantic-settings model — values are loaded from environment / ``.env``."""

    APP_NAME: str = "async-pulse"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENV: str = "development"

    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./async_pulse.db"
    # Optional direct (non-pooled) URL used by Alembic for DDL migrations.
    # Required when DATABASE_URL points at a pgbouncer transaction pooler
    # (e.g. Supabase port 6543) that silently drops DDL.
    # If not set, env.py attempts to auto-derive it; set explicitly when
    # auto-derivation fails (e.g. custom domains, IPv6, non-standard hostnames).
    DIRECT_DATABASE_URL: str | None = None
    DB_SCHEMA: str = "public"

    # ── Redis ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Auth ──────────────────────────────────────────────
    SECRET_KEY: str  # Must be provided via environment or .env
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Refresh Token Cookie ──────────────────────────────
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_DOMAIN: str | None = None
    REFRESH_COOKIE_SECURE: bool = False
    REFRESH_COOKIE_HTTPONLY: bool = True
    REFRESH_COOKIE_SAMESITE: str = "lax"

    # ── CORS ──────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── Logging ───────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── API ───────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"

    model_config = {"env_file": ".env", "extra": "forbid"}

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Reject weak secrets in non-development environments."""
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        return v


@lru_cache
def get_settings() -> Settings:
    """Return the cached ``Settings`` singleton."""
    return Settings()
