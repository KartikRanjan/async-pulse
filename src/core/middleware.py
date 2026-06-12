"""CORS middleware configuration.

CORS is configured via FastAPI's ``add_middleware`` in ``main.py``.
This module centralises the middleware constructor for reuse/testing.
"""

from fastapi.middleware.cors import CORSMiddleware

from src.core.settings import get_settings


def add_cors_middleware(app) -> None:  # noqa: ANN001 — FastAPI type circular
    """Add CORS middleware to *app* using settings."""
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
