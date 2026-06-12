"""Auth repository — lightweight data access for authentication operations.

Uses the user repository under the hood. In a larger system this might
query a dedicated ``refresh_tokens`` table; here it delegates to the
user repository for simplicity.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.repository import UserRepository


class AuthRepository:
    """Authentication-specific data access (thin wrapper)."""

    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
