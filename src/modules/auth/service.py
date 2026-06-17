"""Auth service — authentication use-case logic, framework-agnostic.

Depends on user repository for credential verification and
``shared/security`` for JWT operations.
"""

from src.modules.auth.exceptions import InvalidCredentialsError, InvalidTokenError
from src.modules.auth.schemas import TokenPair, TokenRefreshRequest
from src.modules.users.repository import UserRepository
from src.shared.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)


class AuthService:
    """Orchestrates login and token refresh operations."""

    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def authenticate(self, email: str, password: str) -> TokenPair:
        """Verify credentials and return a token pair. Raises ``InvalidCredentials`` on failure."""
        user = await self.user_repository.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()

        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    def refresh_token(self, request: TokenRefreshRequest) -> TokenPair:
        """Validate a refresh token and return a new token pair.

        Raises ``InvalidTokenError`` on failure.
        """
        try:
            payload = decode_token(request.refresh_token)
        except Exception as exc:
            raise InvalidTokenError("Invalid or expired refresh token") from exc

        if payload.get("type") != "refresh":
            raise InvalidTokenError("Token is not a refresh token")

        subject = payload.get("sub")
        if not subject:
            raise InvalidTokenError("Invalid token payload")

        return TokenPair(
            access_token=create_access_token(subject),
            refresh_token=create_refresh_token(subject),
        )
