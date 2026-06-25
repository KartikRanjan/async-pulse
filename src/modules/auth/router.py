"""Auth HTTP routes — thin layer, no business logic.

Domain exceptions are caught by the central handler in
``core/exception_handlers.py``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from src.core.settings import get_settings
from src.modules.auth.dependencies import get_auth_service, get_current_user, oauth2_scheme
from src.modules.auth.schemas import LoginRequest, TokenPair, TokenRefreshRequest
from src.modules.auth.service import AuthService
from src.modules.users.entities import User
from src.shared.logger import get_logger
from src.shared.responses import SuccessResponse
from src.shared.security import decode_token

router = APIRouter()

logger = get_logger(__name__)
settings = get_settings()

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an httpOnly secure cookie."""
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=settings.REFRESH_COOKIE_HTTPONLY,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )


@router.post("/login", response_model=SuccessResponse[TokenPair])
async def login(
    payload: LoginRequest,
    service: AuthServiceDep,
    request: Request,
    response: Response,
) -> SuccessResponse[TokenPair]:
    """Authenticate a user and return a JWT token pair, creating a session.

    The refresh token is set as an httpOnly cookie AND returned in the body
    so both browser and non-browser clients can authenticate.
    """
    device_info = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    token_pair = await service.authenticate(
        payload.email,
        payload.password,
        device_info=device_info,
        ip_address=ip_address,
    )

    _set_refresh_cookie(response, token_pair.refresh_token)

    return SuccessResponse(
        data=token_pair,
        message="Login successful",
    )


@router.post("/refresh", response_model=SuccessResponse[TokenPair])
async def refresh_token(
    service: AuthServiceDep,
    request: Request,
    response: Response,
    body: TokenRefreshRequest | None = None,
) -> SuccessResponse[TokenPair]:
    """Refresh an access token using a valid refresh token with rotation.

    Reads the refresh token from the httpOnly cookie first, falling back
    to the request body for non-browser clients.
    """
    token_str: str | None = None
    if body and body.refresh_token:
        token_str = body.refresh_token
    else:
        token_str = request.cookies.get(settings.REFRESH_COOKIE_NAME)

    if not token_str:
        from src.modules.auth.exceptions import InvalidTokenError

        raise InvalidTokenError("Refresh token not provided")

    ip_address = request.client.host if request.client else None

    token_pair = await service.refresh_token(
        TokenRefreshRequest(refresh_token=token_str),
        ip_address=ip_address,
    )

    _set_refresh_cookie(response, token_pair.refresh_token)

    return SuccessResponse(
        data=token_pair,
        message="Token refreshed successfully",
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    service: AuthServiceDep,
    authorization: str = Depends(oauth2_scheme),
) -> None:
    """Revoke the current authentication session and clear the refresh cookie."""
    _clear_refresh_cookie(response)

    try:
        payload = decode_token(authorization)
        session_id = payload.get("sid")
        if session_id:
            await service.logout(session_id)
    except Exception as exc:
        logger.warning("logout_session_failed", error=str(exc))


@router.post("/logout-all", status_code=204)
async def logout_all(
    response: Response,
    service: AuthServiceDep,
    current_user: CurrentUserDep,
) -> None:
    """Revoke all active authentication sessions for the user and clear the cookie."""
    _clear_refresh_cookie(response)
    await service.logout_all(current_user.id)
