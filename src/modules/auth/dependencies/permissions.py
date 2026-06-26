"""Authorization (RBAC) — enforcing *what you are allowed to do*.

Builds on authentication (``get_current_user``) and the domain role hierarchy
(``ROLE_HIERARCHY``, owned by the users module). Any protected route in any
module can require a minimum role:

    from src.modules.auth.dependencies import require_role, AdminDep
    from src.modules.users.entities import UserRole

    @router.delete("/{id}")
    async def delete_thing(_: AdminDep): ...
    # or, explicitly:
    async def delete_thing(_: User = Depends(require_role(UserRole.SUPERUSER))): ...
"""

from typing import Annotated

from fastapi import Depends

from src.modules.users.entities import ROLE_HIERARCHY, User, UserRole
from src.modules.users.exceptions import InsufficientPermissionsError

from .authentication import get_current_user


class RoleGuard:
    """FastAPI dependency callable for hierarchical RBAC authorization."""

    def __init__(self, required_role: UserRole) -> None:
        self.required_role = required_role

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        """Enforce that the authenticated user meets the minimum required role."""
        current_val = ROLE_HIERARCHY.get(current_user.role, 0)
        required_val = ROLE_HIERARCHY.get(self.required_role, 0)

        if current_val < required_val:
            raise InsufficientPermissionsError(
                f"Requires at least {self.required_role} role permissions"
            )
        return current_user


def require_role(role: UserRole) -> RoleGuard:
    """Return a security dependency requiring the given hierarchical role."""
    return RoleGuard(role)


# Ready-to-use dependency aliases for the common role gates.
AdminDep = Annotated[User, Depends(require_role(UserRole.ADMIN))]
SuperuserDep = Annotated[User, Depends(require_role(UserRole.SUPERUSER))]
