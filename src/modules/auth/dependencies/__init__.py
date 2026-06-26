"""Authentication and authorization dependencies sub-package."""

from .authentication import CurrentUserDep, get_current_user, oauth2_scheme
from .permissions import AdminDep, RoleGuard, SuperuserDep, require_role
from .providers import get_auth_repository, get_auth_service

__all__ = [
    "AdminDep",
    "CurrentUserDep",
    "RoleGuard",
    "SuperuserDep",
    "get_auth_repository",
    "get_auth_service",
    "get_current_user",
    "oauth2_scheme",
    "require_role",
]
