"""Application lifespan — startup and shutdown hooks.

Called once by FastAPI via ``app = FastAPI(lifespan=lifespan)``.

Schema is owned by Alembic migrations (``alembic upgrade head``), not the
application. Startup assumes the database is already migrated — it does not
run ``create_all``, so the migration history stays the single source of truth.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.db.session import engine
from src.shared.logger import get_logger, setup_logging

log = get_logger("lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: configure logging. Shutdown: close cache and dispose the engine."""
    setup_logging()
    log.info("Starting up", app_name=app.title, version=app.version)

    yield

    log.info("Shutting down")
    from src.core.cache import get_cache_client

    await get_cache_client().close()
    await engine.dispose()
