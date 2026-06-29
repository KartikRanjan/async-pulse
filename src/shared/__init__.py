"""Shared utilities — pure, framework-free helpers used across all modules.

Nothing in this package may import from ``src.modules``.
"""

from src.shared.schemas import CamelModel

__all__ = ["CamelModel"]
