"""User schemas — Pydantic DTOs for API request/response.

Internal schemas (prefixed with underscore) are used between layers
but never exposed over HTTP.
"""

from datetime import datetime

from pydantic import ConfigDict, EmailStr, Field

from src.modules.users.entities import UserRole, UserStatus
from src.shared import CamelModel

# ── Response schemas (public) ─────────────────────────────


class UserRead(CamelModel):
    """Public user representation returned by the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    email: EmailStr
    username: str
    name: str
    status: UserStatus
    role: UserRole
    # Public field stays ``is_active``; sourced from the entity's renamed
    # ``is_fully_active`` property (ACTIVE + not soft-deleted).
    is_active: bool = Field(validation_alias="is_fully_active")
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


# ── Request schemas (public) ──────────────────────────────


class UserCreate(CamelModel):
    """Payload for creating a new user."""

    email: EmailStr
    name: str = Field(min_length=3, max_length=100)
    username: str = Field(min_length=3, max_length=25)
    password: str = Field(min_length=8)


class UserUpdate(CamelModel):
    """Payload for partial user update — all fields optional."""

    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=100)
