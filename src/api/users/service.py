"""
User management business logic.
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password, verify_password
from src.models.user import User
from src.schemas.user import PasswordChange, UserUpdate


async def get_user_by_id(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def list_users(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
    """Return paginated users and total count."""
    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    return list(result.scalars().all()), total


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    """Apply partial updates to a user."""
    update_data = data.model_dump(exclude_unset=True)

    if "email" in update_data:
        existing = await db.execute(select(User).where(User.email == update_data["email"]))
        if existing.scalar_one_or_none() and existing.scalar_one().id != user.id:
            raise HTTPException(status_code=409, detail="Email already in use")

    if "username" in update_data:
        existing = await db.execute(select(User).where(User.username == update_data["username"]))
        if existing.scalar_one_or_none() and existing.scalar_one().id != user.id:
            raise HTTPException(status_code=409, detail="Username already taken")

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    return user


async def change_password(db: AsyncSession, user: User, data: PasswordChange) -> None:
    """Verify current password and set new one."""
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    user.hashed_password = hash_password(data.new_password)
    await db.flush()


async def delete_user(db: AsyncSession, user: User) -> None:
    """Soft-disable a user."""
    user.is_active = False
    await db.flush()
