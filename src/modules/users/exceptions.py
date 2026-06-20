"""User domain exceptions — inherit from ``AppError`` base classes.

Central handler translates these into HTTP responses — never raise
``HTTPException`` from service/repository layers.
"""

from src.shared.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
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


class UserDeactivationError(ValidationError):
    """Raised when a user tries to deactivate their own account."""

    def __init__(self) -> None:
        super().__init__("Cannot deactivate your own account")


class UserAlreadyInactiveError(ValidationError):
    """Raised when attempting to deactivate an already inactive user."""

    def __init__(self, user_id: str = "") -> None:
        detail = f"User is already inactive: {user_id}" if user_id else "User is already inactive"
        super().__init__(detail)


class InvalidStatusTransitionError(ValidationError):
    """Raised when an invalid status transition is attempted."""

    def __init__(self, user_id: str, from_status: str, to_status: str) -> None:
        detail = f"Cannot transition user {user_id} from {from_status} to {to_status}"
        super().__init__(detail)


class UserSuspendedError(AuthenticationError):
    """Raised when a suspended user tries to authenticate."""

    def __init__(self, detail: str = "User account has been suspended") -> None:
        super().__init__(detail)


class UserBannedError(AuthenticationError):
    """Raised when a banned user tries to authenticate."""

    def __init__(self, detail: str = "User account has been banned") -> None:
        super().__init__(detail)


class UserNotVerifiedError(AuthenticationError):
    """Raised when a user attempts actions requiring verification."""

    def __init__(self, detail: str = "User email has not been verified") -> None:
        super().__init__(detail)
