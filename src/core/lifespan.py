"""Application lifespan — startup and shutdown hooks.

Called once by FastAPI via ``app = FastAPI(lifespan=lifespan)``.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from src.core.settings import get_settings
from src.db.base import Base
from src.db.session import engine
from src.shared.logger import get_logger, setup_logging

settings = get_settings()
log = get_logger("lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: configure logging + create tables. Shutdown: dispose engine."""
    setup_logging()
    log.info("Starting up", app_name=app.title, version=app.version)

    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"'))
        await conn.run_sync(Base.metadata.create_all)

    log.info("Database tables created")
    yield

    log.info("Shutting down")
    from src.core.cache import get_cache_client

    await get_cache_client().close()
    await engine.dispose()
