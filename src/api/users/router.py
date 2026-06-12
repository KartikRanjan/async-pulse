"""
User management API routes.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.users.service import (
    change_password,
    delete_user,
    get_user_by_id,
    list_users,
    update_user,
)
from src.config.database import get_db
from src.core.deps import get_current_user
from src.models.user import User
from src.schemas.user import PaginatedUsers, PasswordChange, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile fields."""
    return await update_user(db, current_user, body)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_current_password(
    body: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    await change_password(db, current_user, body)


@router.get("/", response_model=PaginatedUsers)
async def read_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List all users (paginated, requires auth)."""
    users, total = await list_users(db, page, page_size)
    return PaginatedUsers(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserRead)
async def read_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get a specific user by ID (requires auth)."""
    return await get_user_by_id(db, user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def admin_update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin: update any user's fields."""
    target = await get_user_by_id(db, user_id)
    return await update_user(db, target, body)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin: soft-delete (disable) a user."""
    target = await get_user_by_id(db, user_id)
    await delete_user(db, target)
