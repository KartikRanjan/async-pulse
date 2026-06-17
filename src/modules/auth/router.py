"""Auth HTTP routes — thin layer, no business logic.

Domain exceptions are caught by the central handler in
``core/exception_handlers.py``.
"""

from fastapi import APIRouter, Depends

from src.modules.auth.dependencies import get_auth_service
from src.modules.auth.schemas import LoginRequest, TokenPair, TokenRefreshRequest
from src.modules.auth.service import AuthService
from src.shared.responses import SuccessResponse

router = APIRouter()


@router.post("/login", response_model=SuccessResponse[TokenPair])
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[TokenPair]:
    """Authenticate a user and return a JWT token pair."""
    token_pair = await service.authenticate(payload.email, payload.password)
    return SuccessResponse(
        data=token_pair,
        message="Login successful",
    )


@router.post("/refresh", response_model=SuccessResponse[TokenPair])
async def refresh_token(
    payload: TokenRefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[TokenPair]:
    """Refresh an access token using a valid refresh token."""
    token_pair = service.refresh_token(payload)
    return SuccessResponse(
        data=token_pair,
        message="Token refreshed successfully",
    )

