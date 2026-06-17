"""Standardized API response envelopes.

Factories mirror the TypeScript response helpers — every endpoint returns
a consistent ``{ success, message, data }`` (or error) shape.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


# ── Response models ──────────────────────────────────────


class SuccessResponse[T](BaseModel):
    """Envelope for successful responses."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(serialization_alias=to_camel),
        populate_by_name=True,
    )

    success: bool = True
    message: str
    data: T
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


class ErrorResponse(BaseModel):
    """Envelope for error responses."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(serialization_alias=to_camel),
        populate_by_name=True,
    )

    success: bool = False
    message: str
    error_code: str
    errors: list[Any] | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


def success_response(data: object, message: str = "Operation successful") -> dict[str, Any]:
    """Build a success response (matches TypeScript factory)."""
    return SuccessResponse(data=data, message=message).model_dump(by_alias=True)


def error_response(
    message: str = "An unexpected error occurred",
    error_code: str = "INTERNAL_ERROR",
    errors: list[Any] | None = None,
) -> dict[str, Any]:
    """Build an error response (matches TypeScript factory)."""
    # Ensure empty lists are treated as None so they are excluded
    errors_to_include = errors if errors and len(errors) > 0 else None

    return ErrorResponse(
        message=message,
        error_code=error_code,
        errors=errors_to_include,
    ).model_dump(by_alias=True, exclude_none=True)
