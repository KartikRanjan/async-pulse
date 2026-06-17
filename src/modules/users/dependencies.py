"""User DI composition — wires repository + UoW into UserService.

Each router declares its own DI functions (CODING_CONVENTIONS §9).
"""

from fastapi import Depends

from src.db.unit_of_work import UnitOfWork, get_unit_of_work
from src.modules.users.service import UserService


async def get_user_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> UserService:
    """FastAPI dependency — yields a ``UserService`` with its UoW."""
    return UserService(uow)
