"""Central exception handlers — domain exceptions → HTTP responses.

Register once in ``main.py`` via ``app.add_exception_handler(AppError, app_error_handler)``.
"""

import http
import re
from functools import lru_cache

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.shared.exceptions import AppError
from src.shared.logger import get_logger
from src.shared.responses import error_response

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _status_code_map() -> dict[int, str]:
    """Build a reverse map from HTTP status → UPPER_SNAKE name, e.g. 404 → 'NOT_FOUND'."""
    return {code.value: code.phrase.replace(" ", "_").upper() for code in http.HTTPStatus}


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle FastAPI HTTPExceptions with standardized error envelope."""
    if not isinstance(exc, HTTPException):  # pragma: no cover - registered per type
        raise exc
    detail = exc.detail
    path = request.url.path

    if exc.status_code == 404:
        if path.startswith("//"):
            detail = (
                f"Route not found: '{path}'. "
                "Hint: possible double-slash in URL. "
                "Ensure base URL has no trailing slash "
                "(e.g., 'http://localhost:8000' not 'http://localhost:8000/')."
            )
        else:
            detail = f"Route not found: {path}"

    error_code = _status_code_map().get(exc.status_code, "HTTP_ERROR")

    content = error_response(message=detail, error_code=error_code)
    return JSONResponse(status_code=exc.status_code, content=content)


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Translate any ``AppError`` subclass into a standardized JSON response."""
    if not isinstance(exc, AppError):  # pragma: no cover - registered per type
        raise exc
    if exc.error_code:
        error_code = exc.error_code.upper()
    else:
        # Fallback: snake_case from class name — NOTFOUND → NOT_FOUND
        raw = exc.__class__.__name__.replace("Error", "")
        error_code = re.sub(r"([A-Z])", r"_\1", raw).lstrip("_").upper()

    content = error_response(message=exc.message, error_code=error_code)
    return JSONResponse(status_code=exc.status_code, content=content)


async def validation_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle FastAPI input validation errors with standardized error envelope."""
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    content = error_response(
        message="Validation failed",
        error_code="VALIDATION_FAILED",
        errors=list(exc.errors()),
    )
    return JSONResponse(status_code=422, content=content)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions with standardized 500 response and server log."""
    logger.exception(
        "Unhandled exception occurred",
        path=request.url.path,
        method=request.method,
    )
    content = error_response(
        message="An unexpected error occurred",
        error_code="INTERNAL_SERVER_ERROR",
    )
    return JSONResponse(status_code=500, content=content)
