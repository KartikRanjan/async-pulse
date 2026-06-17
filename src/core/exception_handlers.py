"""Central exception handlers — domain exceptions → HTTP responses.

Register once in ``main.py`` via ``app.add_exception_handler(AppError, app_error_handler)``.
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from src.shared.exceptions import AppError
from src.shared.responses import error_response


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle FastAPI HTTPExceptions with standardized error envelope."""
    assert isinstance(exc, HTTPException)
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

    content = error_response(message=detail, error_code="HTTP_EXCEPTION")
    return JSONResponse(status_code=exc.status_code, content=content)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate any ``AppError`` subclass into a standardized JSON response."""
    assert isinstance(exc, AppError)
    error_code = exc.__class__.__name__.replace("Error", "").upper()
    if not error_code:
        error_code = "APP_ERROR"

    content = error_response(
        message=exc.message,
        error_code=f"{error_code}_ERROR" if not error_code.endswith("ERROR") else error_code,
    )

    return JSONResponse(status_code=exc.status_code, content=content)
