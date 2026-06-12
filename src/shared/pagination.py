"""Reusable pagination helpers.

``PageParams`` is a FastAPI dependency that extracts ``page`` / ``page_size``
from query parameters.  ``PagedResponse`` is a generic base for paginated
response envelopes.
"""

from typing import TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class PageParams:
    """FastAPI dependency — extract pagination params from query string."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


class PagedResponse[T](BaseModel):
    """Generic paged response envelope."""

    items: list[T]
    total: int
    page: int
    page_size: int
