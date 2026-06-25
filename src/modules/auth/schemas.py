"""Auth schemas — Pydantic DTOs for authentication API."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Login payload."""

    email: str
    password: str


class TokenPair(BaseModel):
    """JWT token pair returned after login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    """Refresh token payload."""

    refresh_token: str
