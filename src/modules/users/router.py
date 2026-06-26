"""User HTTP routes — thin layer, no business logic.

All domain exceptions are caught by the central handler in
``core/exception_handlers.py`` — no try/except here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.modules.auth import get_current_user, require_role
from src.modules.users.dependencies import get_user_service
from src.modules.users.entities import User, UserRole
from src.modules.users.exceptions import InsufficientPermissionsError
from src.modules.users.schemas import UserCreate, UserRead, UserUpdate
from src.modules.users.service import UserService
from src.shared.pagination import PagedResponse, PageParams
from src.shared.responses import SuccessResponse

router = APIRouter()

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post("/", response_model=SuccessResponse[UserRead], status_code=201)
async def create_user(
    payload: UserCreate,
    service: UserServiceDep,
) -> SuccessResponse[UserRead]:
    """Register a new user."""
    user = await service.create_user(payload)
    return SuccessResponse(
        data=UserRead.model_validate(user),
        message="User created successfully",
    )


@router.get("/", response_model=SuccessResponse[PagedResponse[UserRead]])
async def list_users(
    service: UserServiceDep,
    pagination: PageParams = Depends(),
) -> SuccessResponse[PagedResponse[UserRead]]:
    """List all users with pagination."""
    users, total = await service.list_users(pagination.offset, pagination.page_size)
    return SuccessResponse(
        data=PagedResponse(
            items=[UserRead.model_validate(u) for u in users],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
        message="Users retrieved successfully",
    )


@router.get("/{user_id}", response_model=SuccessResponse[UserRead])
async def get_user(
    user_id: str,
    service: UserServiceDep,
) -> SuccessResponse[UserRead]:
    """Get a user by ID."""
    user = await service.get_user(user_id)
    return SuccessResponse(
        data=UserRead.model_validate(user),
        message="User retrieved successfully",
    )


@router.patch("/{user_id}", response_model=SuccessResponse[UserRead])
async def update_user(
    user_id: str,
    payload: UserUpdate,
    service: UserServiceDep,
    current_user: CurrentUserDep,
) -> SuccessResponse[UserRead]:
    """Update a user. Requires profile ownership or superuser privileges."""
    if current_user.id != user_id and current_user.role != UserRole.SUPERUSER:
        raise InsufficientPermissionsError("Cannot update other users' profile")

    user = await service.update_user(user_id, payload, current_user_id=current_user.id)
    return SuccessResponse(
        data=UserRead.model_validate(user),
        message="User updated successfully",
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    service: UserServiceDep,
    _current_user: User = Depends(require_role(UserRole.SUPERUSER)),  # noqa: B008
) -> None:
    """Soft-delete a user. Requires superuser privileges."""
    await service.delete_user(user_id)
