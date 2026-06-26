# Cross-Module User Table Ownership (Auth ↔ Users)

> How the `auth` and `users` modules share the user record without breaking
> module isolation. Documents the **implemented approach (Option A)** and the
> **future stronger boundary (Option B)**.

---

## 1. Problem

Both `auth` and `users` need the same user record:

- **`users`** owns identity/profile concerns — email, username, profile updates,
  listing, soft-delete.
- **`auth`** needs credentials and account status to log a user in, rotate
  refresh tokens, and gate access (`hashed_password`, `status`, `role`).

The original implementation gave each module its **own repository writing the
same `users` table**. `AuthRepository` imported `UserModel` directly:

```python
# auth/repository.py (before)
from src.modules.users.models import UserModel   # ← cross-module model import

select(UserModel).where(UserModel.email == email)
```

Field-level privilege was enforced with runtime guards (each repository rejected
the other's fields), but the design had real problems:

1. **Violated module isolation.** `AGENTS.md` states: _"Never import another
   module's repository, models, or internal routers directly."_ Auth reached past
   the users module's public surface into its persistence model.
2. **Two owners of one table.** A schema change in `users` could silently break
   `auth`. The boundary existed at the field level but the coupling lived at the
   table level.
3. **Drift between paths.** `users` reads filtered `deleted_at IS NULL`; the auth
   identity reads did not. Two repositories over one table let these diverge.

---

## 2. Implemented Approach — Option A: Single Owner + Service-to-Service

The `users` module is the **sole owner** of `UserModel` and the `users` table.
Any other module that needs user data — including `auth` — goes through the
public `UserService`. Auth keeps exclusive ownership of its own `sessions` table.

```text
auth.router → auth.service ──▶ users.service ──▶ users.repository ──▶ users table
                   │
                   └──────────▶ auth.repository ──────────────────▶ sessions table
```

### What changed

**`users` module — added privileged, single-owner write operations.**

`UserRepository` gained explicit credential/status methods, kept separate from
the profile-only `update()` (which still forbids `hashed_password`, `status`,
`role`). This preserves field-level least privilege _inside_ the owning module:

```python
# users/repository.py
async def set_credentials(self, user_id: str, *, hashed_password: str) -> User: ...
async def set_status(self, user_id: str, *, status: UserStatus) -> User: ...
```

`UserService` exposes these as the public, cross-module API. `change_status`
routes through the `User` entity's state machine so invariants hold regardless of
caller:

```python
# users/service.py
async def set_password(self, user_id: str, new_password: str) -> User: ...
async def change_status(self, user_id: str, new_status: UserStatus) -> User:
    user = await self.repo.get_by_id(user_id)
    if not user:
        raise UserNotFoundError(user_id)
    user.transition_to(new_status)          # entity enforces valid transitions
    updated = await self.repo.set_status(user_id, status=user.status)
    await self.uow.commit()
    ...
```

**`auth` module — stopped touching `UserModel`.**

- `AuthRepository` no longer imports `UserModel`. It owns the `sessions` table
  only (RTR session create/read/update/revoke). The `get_identity_*` and
  `update_identity` methods were removed.
- `AuthService` now depends on `UserService` for identity reads:

  ```python
  # auth/service.py (after)
  user = await self.users.get_user_by_email(email)
  if not user or not verify_password(password, user.hashed_password):
      raise InvalidCredentialsError()
  ```

- The now-unused `AuthIdentity` entity (a projection that existed only to support
  direct table access) was removed, along with its public export.

**Dependency wiring.** `AuthService` reached 4 collaborators, so per the
"3+ dependencies → frozen dataclass" convention they are grouped:

```python
# auth/service.py
@dataclass(frozen=True)
class AuthServiceDeps:
    repository: AuthRepository
    user_service: UserService
    uow: UnitOfWork
    cache: CacheClient
```

```python
# auth/dependencies.py — wiring only
async def get_auth_service(
    repository: AuthRepository = Depends(get_auth_repository),
    user_service: UserService = Depends(get_user_service),
    uow: UnitOfWork = Depends(get_unit_of_work),
    cache: CacheClient = Depends(get_cache_client),
) -> AuthService:
    return AuthService(
        deps=AuthServiceDeps(
            repository=repository,
            user_service=user_service,
            uow=uow,
            cache=cache,
        ),
    )
```

### Why this is safe transactionally

FastAPI caches dependencies per request, so `get_async_session` and
`get_unit_of_work` resolve to the **same** `AsyncSession` and `UnitOfWork` for
both `UserRepository` and `AuthRepository`. A flow that touches both tables
(e.g. issuing a session while updating credentials) shares one transaction and
commits atomically through the single Unit of Work.

### Benefits realized

- **Isolation restored.** No module imports another module's persistence model.
  The only cross-module dependency is `auth.service → users.service`, which is
  the sanctioned `A's service calls B's service` pattern.
- **One owner per table.** `users` owns `users`; `auth` owns `sessions`.
- **Consistency fixed.** Identity reads now use `UserService`, which filters
  `deleted_at IS NULL`. A soft-deleted user is no longer found by auth, removing
  the previous read-path divergence.
- **Privilege preserved.** Credential/status writes still live behind explicit,
  named operations — not a generic `update()` that mutates arbitrary fields.

### Trade-offs

- The `users` and `auth` modules still share **one physical table row** for a
  user; the boundary is logical (service ownership), not physical.
- Auth login does one extra service hop instead of a direct query (negligible;
  same session, same transaction).

---

## 3. Future Approach — Option B: Physical Table Separation

When auth state grows (email-verification tokens, password-reset tokens, lockout
counters, MFA secrets), bloating the `users` table with auth-only columns becomes
the new smell. At that point, give each module its **own table**.

### Shape

- `users` table — identity/profile: `email`, `username`, `role`, `deleted_at`,
  timestamps.
- `auth_credentials` table (owned by `auth`) — `user_id` FK, `hashed_password`,
  `status`, and future security fields. One-to-one with `users`.
- `sessions` table — unchanged, owned by `auth`.

```text
users table ◀── users.repository ◀── users.service        (profile/identity)
auth_credentials table ◀── auth.repository ◀── auth.service (credentials/status)
sessions table         ◀── auth.repository ◀── auth.service (RTR sessions)
```

### Benefits

- **Hard boundary.** Each module owns its tables outright. No shared row, no
  runtime field guards, no service hop needed for auth's own credential writes.
- **Extraction-ready.** Closest to a future split into independent services —
  auth could become its own deployable with its own datastore.
- **Schema independence.** Profile schema changes can't affect auth and vice
  versa.

### Costs

- A migration to move `hashed_password`/`status` out of `users` into
  `auth_credentials` (data backfill + FK + the `sessions.user_id` relationship
  to reconcile).
- Login/refresh need a join or a second lookup to combine profile + credentials.
- Status now lives in auth; any users-side logic reading `status` must call
  `auth.service` (the inverse cross-module dependency of today).

### When to promote

Adopt Option B once **any** of these is true:

- Auth needs 2+ new security columns (verification/reset tokens, lockout, MFA).
- `users` and `auth` schema changes start blocking each other.
- A genuine plan exists to extract `auth` into a separate service.

Until then, Option A keeps the boundary clean with minimal moving parts.

---

## 4. Rules of Thumb

- A database table has exactly **one owning module**. Others access it through
  that module's **service**, never its repository or model.
- Security-sensitive columns get **explicit, named** write operations
  (`set_password`, `change_status`) — never a generic field-spreading `update()`.
- Cross-module calls go **service → service** and rely on the per-request shared
  `AsyncSession` / `UnitOfWork` for atomicity.
