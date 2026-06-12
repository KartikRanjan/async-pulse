"""Application settings — pydantic-settings with .env support.

Module-level singleton via ``@lru_cache`` (CODING_CONVENTIONS §16).
Never constructor-injected.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Pydantic-settings model — values are loaded from environment / ``.env``."""

    APP_NAME: str = "async-pulse"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./async_pulse.db"

    # ── Auth ──────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION"  # noqa: S105
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ──────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["*"]

    # ── Logging ───────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── API ───────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"

    model_config = {"env_file": ".env", "extra": "forbid"}


@lru_cache
def get_settings() -> Settings:
    """Return the cached ``Settings`` singleton."""
    return Settings()
