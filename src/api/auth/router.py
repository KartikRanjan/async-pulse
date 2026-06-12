"""
Auth API routes — register, login, refresh.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.service import authenticate_user, issue_tokens, refresh_access_token, register_user
from src.config.database import get_db
from src.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    Token,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    user = await register_user(db, body)
    return RegisterResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
    )


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return JWT tokens."""
    user = await authenticate_user(db, body.email, body.password)
    return issue_tokens(user)


@router.post("/refresh", response_model=Token)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new token pair."""
    return await refresh_access_token(db, body.refresh_token)
