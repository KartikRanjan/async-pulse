"""Auth HTTP routes — thin layer, no business logic.

Domain exceptions are caught by the central handler in
``core/exception_handlers.py``.
"""

from fastapi import APIRouter, Depends

from src.modules.auth.dependencies import get_auth_service
from src.modules.auth.schemas import LoginRequest, TokenPair, TokenRefreshRequest
from src.modules.auth.service import AuthService

router = APIRouter()


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),  # noqa: B008
) -> TokenPair:
    """Authenticate a user and return a JWT token pair."""
    return await service.authenticate(payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    payload: TokenRefreshRequest,
    service: AuthService = Depends(get_auth_service),  # noqa: B008
) -> TokenPair:
    """Refresh an access token using a valid refresh token."""
    return service.refresh_token(payload)
