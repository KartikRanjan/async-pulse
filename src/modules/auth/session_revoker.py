"""Session revocation adapter for cross-module use.

Other modules (e.g. ``users``) sometimes need to forcibly terminate a user's
sessions — for instance when an account is suspended, banned, or soft-deleted.
Those modules depend on the ``SessionRevoker`` *port* (defined in the consuming
module) and receive this adapter via dependency injection, so they never import
the auth repository or models directly.

The adapter intentionally depends on nothing from the ``users`` module, which
keeps the dependency direction one-way (auth → users) and avoids import cycles.
It does not open or commit a transaction: it flushes via the shared
``AsyncSession`` and lets the caller's Unit of Work own the commit, so the
session revocation is atomic with whatever change triggered it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import CacheClient
from src.modules.auth.repository import AuthRepository


class AuthSessionRevoker:
    """Revokes all of a user's sessions and clears their cached session state."""

    def __init__(self, repository: AuthRepository, cache: CacheClient) -> None:
        self._repo = repository
        self._cache = cache

    async def revoke_user_sessions(self, user_id: str) -> None:
        """Revoke every active session for ``user_id`` and purge its caches.

        DB rows are revoked via ``flush`` (the caller commits); session and grace
        cache keys are deleted so the cache-aside session check cannot serve a
        revoked session as active.
        """
        active_sessions = await self._repo.get_active_sessions_for_user(user_id)
        await self._repo.revoke_all_sessions(user_id)
        for session in active_sessions:
            await self._cache.delete(f"session:{session.id}")
            await self._cache.delete(f"grace:{session.id}")


def build_session_revoker(session: AsyncSession, cache: CacheClient) -> AuthSessionRevoker:
    """Construct an ``AuthSessionRevoker`` bound to the given session and cache.

    Public factory so consuming modules can compose a revoker without importing
    the auth repository directly.
    """
    return AuthSessionRevoker(repository=AuthRepository(session), cache=cache)
