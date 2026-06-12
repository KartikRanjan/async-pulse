"""
Declarative base for all SQLAlchemy models.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class — import all models so Alembic / metadata sees them."""

    pass
