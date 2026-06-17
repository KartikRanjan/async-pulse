"""Shared constants, enums, and string literals."""

from enum import StrEnum


class TokenType(StrEnum):
    """Token type constants for JWT claims."""

    ACCESS = "access"
    REFRESH = "refresh"
