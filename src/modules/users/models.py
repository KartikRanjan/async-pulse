"""SQLAlchemy persistence model for users.

This is the ORM layer only — domain behaviour lives in ``entities.py``.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.modules.users.entities import UserRole, UserStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserModel(Base):
    """User persistence model — maps to the ``users`` table."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus, native_enum=False, length=50),
        default=UserStatus.ACTIVE,
    )
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, native_enum=False, length=50),
        default=UserRole.USER,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )
