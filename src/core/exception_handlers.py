"""Central exception handlers — domain exceptions → HTTP responses.

Register once in ``main.py`` via ``app.add_exception_handler(AppError, app_error_handler)``.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from src.shared.exceptions import AppError


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate any ``AppError`` subclass into a JSON HTTP response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
