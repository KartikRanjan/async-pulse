"""SQLAlchemy declarative base."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from src.core.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Single declarative base — all models inherit from this."""

    metadata = MetaData(schema=settings.DB_SCHEMA)
