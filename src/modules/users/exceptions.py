"""User domain exceptions — inherit from ``AppError`` base classes.

Central handler translates these into HTTP responses — never raise
``HTTPException`` from service/repository layers.
"""

from src.shared.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
)


class UserNotFoundError(NotFoundError):
    """Raised when a user cannot be found by ID."""

    def __init__(self, user_id: str = "") -> None:
        super().__init__("User", user_id)


class UserAlreadyExistsError(ConflictError):
    """Raised when creating a user with a duplicate email or username."""

    def __init__(self, detail: str = "A user with this email or username already exists") -> None:
        super().__init__(detail)


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials are incorrect."""


class InsufficientPermissionsError(AuthorizationError):
    """Raised when the authenticated user lacks required permissions."""
