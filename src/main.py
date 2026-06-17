"""Application entry point.

Creates the FastAPI app, registers middleware, exception handlers,
and mounts the versioned API router.
"""

from fastapi import FastAPI, HTTPException

from src.api.router import api_router
from src.core.exception_handlers import app_error_handler, http_exception_handler
from src.core.lifespan import lifespan
from src.core.middleware import Enhanced404Middleware, add_cors_middleware
from src.core.settings import get_settings
from src.shared.exceptions import AppError

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────
add_cors_middleware(app)
app.add_middleware(Enhanced404Middleware)

# ── Exception handlers ────────────────────────────────────
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# ── Routes ────────────────────────────────────────────────
app.include_router(api_router)
