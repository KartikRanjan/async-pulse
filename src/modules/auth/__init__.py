"""Auth module exports."""

from .dependencies import (
    AdminDep,
    CurrentUserDep,
    SuperuserDep,
    get_current_user,
    require_role,
)
from .entities import UserSession
from .service import AuthService
from .session_revoker import AuthSessionRevoker, build_session_revoker

__all__ = [
    "AdminDep",
    "AuthService",
    "AuthSessionRevoker",
    "CurrentUserDep",
    "SuperuserDep",
    "UserSession",
    "build_session_revoker",
    "get_current_user",
    "require_role",
]
