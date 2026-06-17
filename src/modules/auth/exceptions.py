"""Auth domain exceptions — inherit from ``AppError`` base classes."""

from src.shared.exceptions import AuthenticationError


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials are incorrect."""


class InvalidTokenError(AuthenticationError):
    """Raised when a JWT is invalid or expired."""
