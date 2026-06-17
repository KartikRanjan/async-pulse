"""CORS middleware configuration.

CORS is configured via FastAPI's ``add_middleware`` in ``main.py``.
This module centralises the middleware constructor for reuse/testing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.settings import get_settings
from src.shared.responses import error_response


def add_cors_middleware(app: FastAPI) -> None:
    """Add CORS middleware to *app* using settings."""
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class Enhanced404Middleware(BaseHTTPMiddleware):
    """Catch 404 responses and provide standardized error messages."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Intercept requests to handle 404 responses dynamically."""
        response = await call_next(request)
        path = request.url.path

        if response.status_code == 404:
            if path.startswith("//"):
                detail = (
                    f"Route not found: '{path}'. "
                    "Hint: possible double-slash in URL. "
                    "Ensure base URL has no trailing slash "
                    "(e.g., 'http://localhost:8000' not 'http://localhost:8000/')."
                )
            else:
                detail = f"Route not found: {path}"

            content = error_response(message=detail, error_code="NOT_FOUND")
            return JSONResponse(status_code=404, content=content)

        return response
