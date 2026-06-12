"""User HTTP routes — thin layer, no business logic.

All domain exceptions are caught by the central handler in
``core/exception_handlers.py`` — no try/except here.
"""

from fastapi import APIRouter, Depends

from src.modules.users.dependencies import get_user_service
from src.modules.users.schemas import UserCreate, UserRead, UserUpdate
from src.modules.users.service import UserService
from src.shared.pagination import PagedResponse, PageParams

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),  # noqa: B008
) -> UserRead:
    """Register a new user."""
    user = await service.create_user(payload)
    return UserRead.model_validate(user)


@router.get("/", response_model=PagedResponse[UserRead])
async def list_users(
    pagination: PageParams = Depends(),  # noqa: B008
    service: UserService = Depends(get_user_service),  # noqa: B008
) -> PagedResponse[UserRead]:
    """List all users with pagination."""
    users, total = await service.list_users(pagination.offset, pagination.page_size)
    return PagedResponse(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),  # noqa: B008
) -> UserRead:
    """Get a user by ID."""
    user = await service.get_user(user_id)
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    service: UserService = Depends(get_user_service),  # noqa: B008
) -> UserRead:
    """Update a user."""
    user = await service.update_user(user_id, payload)
    return UserRead.model_validate(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    service: UserService = Depends(get_user_service),  # noqa: B008
) -> None:
    """Delete a user."""
    await service.delete_user(user_id)
