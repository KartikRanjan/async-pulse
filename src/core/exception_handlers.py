"""Central exception handlers — domain exceptions → HTTP responses.

Register once in ``main.py`` via ``app.add_exception_handler(AppError, app_error_handler)``.
"""

import http
import re
from functools import lru_cache

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from src.shared.exceptions import AppError
from src.shared.responses import error_response


@lru_cache(maxsize=1)
def _status_code_map() -> dict[int, str]:
    """Build a reverse map from HTTP status → UPPER_SNAKE name, e.g. 404 → 'NOT_FOUND'."""
    return {code.value: code.phrase.replace(" ", "_").upper() for code in http.HTTPStatus}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTPExceptions with standardized error envelope."""
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


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate any ``AppError`` subclass into a standardized JSON response."""
    if exc.error_code:
        error_code = exc.error_code.upper()
    else:
        # Fallback: snake_case from class name — NOTFOUND → NOT_FOUND
        raw = exc.__class__.__name__.replace("Error", "")
        error_code = re.sub(r"([A-Z])", r"_\1", raw).lstrip("_").upper()

    content = error_response(message=exc.message, error_code=error_code)
    return JSONResponse(status_code=exc.status_code, content=content)
