"""Application entry point.

Creates the FastAPI app, registers middleware, exception handlers,
and mounts the versioned API router.
"""

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from src.api.router import api_router
from src.core.exception_handlers import (
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.core.lifespan import lifespan
from src.core.middleware import add_cors_middleware, add_starlette_error_middleware
from src.core.settings import get_settings
from src.shared.exceptions import AppError
from src.shared.responses import SuccessResponse

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────
add_cors_middleware(app)
add_starlette_error_middleware(app)

# ── Exception handlers ────────────────────────────────────
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


# ── Health check ──────────────────────────────────────────
@app.get("/health", response_model=SuccessResponse[dict[str, str]])
async def health_check() -> SuccessResponse[dict[str, str]]:
    """Liveness probe — returns service status."""
    return SuccessResponse(
        data={"status": "healthy", "version": settings.APP_VERSION},
        message="Service is healthy",
    )


# ── Routes ────────────────────────────────────────────────
app.include_router(api_router)
