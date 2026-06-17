"""Application middleware configuration.

Centralises all middleware constructors for reuse and testing.
Register them in ``main.py`` via the ``add_*`` helpers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

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


def add_starlette_error_middleware(app: FastAPI) -> None:
    """Wrap Starlette-level 404/405 responses in the standard error envelope.

    Starlette returns plain-text responses for unmatched routes and methods,
    bypassing FastAPI's registered exception handlers.  This middleware
    intercepts those responses and re-wraps them consistently.
    """

    @app.middleware("http")
    async def _catch_starlette_errors(
        request: Request, call_next: object
    ) -> JSONResponse:
        response = await call_next(request)  # type: ignore[operator]
        if response.status_code == 404:
            path = request.url.path
            return JSONResponse(
                status_code=404,
                content=error_response(
                    message=f"Route not found: {path}", error_code="NOT_FOUND"
                ),
            )
        if response.status_code == 405:
            return JSONResponse(
                status_code=405,
                content=error_response(
                    message="Method not allowed", error_code="METHOD_NOT_ALLOWED"
                ),
            )
        return response  # type: ignore[return-value]
