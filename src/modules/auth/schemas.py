"""Auth schemas — Pydantic DTOs for authentication API."""

from src.shared.schemas import CamelModel


class LoginRequest(CamelModel):
    """Login payload."""

    email: str
    password: str


class TokenPair(CamelModel):
    """JWT token pair returned after login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(CamelModel):
    """Refresh token payload."""

    refresh_token: str


class UserInfo(CamelModel):
    """Lightweight user info for authenticated requests."""

    user_id: str
    email: str
    name: str
    username: str
    role: str


class LoginResponse(CamelModel):
    """Login response."""

    user_info: UserInfo
    token_pair: TokenPair
