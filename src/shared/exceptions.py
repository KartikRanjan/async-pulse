"""Shared exception hierarchy.

Domain exceptions live in their module's ``exceptions.py`` and inherit from
these base classes.  The central exception handler in ``core/exception_handlers.py``
translates them into HTTP responses exactly once.
"""


class AppError(Exception):
    """Base application error — all domain exceptions inherit from this."""

    error_code: str | None = None

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        *,
        status_code: int = 500,
    ) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    error_code = "NOT_FOUND"

    def __init__(self, resource: str = "Resource", resource_id: str | int = "") -> None:
        detail = f"{resource} not found"
        if resource_id:
            detail += f": {resource_id}"
        super().__init__(detail, status_code=404)


class AuthenticationError(AppError):
    """Raised when authentication fails (bad credentials, expired token, etc.)."""

    error_code = "UNAUTHORIZED"

    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(message, status_code=401)


class AuthorizationError(AppError):
    """Raised when the authenticated principal lacks permission."""

    error_code = "FORBIDDEN"

    def __init__(self, message: str = "Not authorized") -> None:
        super().__init__(message, status_code=403)


class ConflictError(AppError):
    """Raised when an operation conflicts with existing state (e.g. duplicate key)."""

    error_code = "CONFLICT"

    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(message, status_code=409)


class ValidationError(AppError):
    """Raised when business-rule validation fails (distinct from Pydantic schema validation)."""

    error_code = "VALIDATION_FAILED"

    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(message, status_code=422)
