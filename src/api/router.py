"""API router aggregator — mounts module routers under versioned prefix.

This is the single place where module routers are collected and
mounted. Individual routers do NOT set their own prefix.
"""

from fastapi import APIRouter

from src.core.settings import get_settings
from src.modules.auth.router import router as auth_router
from src.modules.users.router import router as users_router

settings = get_settings()

api_router = APIRouter(prefix=settings.API_V1_PREFIX)

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
