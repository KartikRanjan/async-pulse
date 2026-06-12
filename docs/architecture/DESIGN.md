# AsyncPulse — Design Document

> A Python async REST API for user management, built as a learning bridge from
> NestJS/TypeScript to modern Python backend development.

---

## 1. Why This Project

| Concept | NestJS / TypeScript | Python / FastAPI |
|---|---|---|
| Routing | Decorators + `@Controller` | Decorators + `@app.get()` |
| Validation | Zod / class-validator | Pydantic (same concept, native) |
| DI | NestJS IoC container | FastAPI `Depends()` |
| ORM | Drizzle / TypeORM | SQLAlchemy 2.0 ORM |
| Async | Node event loop | Python `async/await` (uvicorn + asyncio) |
| DB Driver | pg (node-postgres) | asyncpg (native async PostgreSQL) |

FastAPI feels familiar coming from NestJS — decorators, DI, typed schemas — but
the async model is explicit `async/await` rather than Node's implicit event loop.

---

> **Architecture note:** This is a **feature-first modular monolith** with layered
> internals (router → application service → domain entity / domain service →
> repository → unit of work → SQLAlchemy ORM → PostgreSQL). It borrows selectively
> from DDD — a thin **domain-entity** layer that holds business behavior, kept
> separate from persistence models, plus an explicit **Unit of Work** for
> transaction boundaries. It deliberately stops short of full DDD (no aggregates,
> value objects, or domain events) to stay simple and onboarding-friendly. We call
> this "DDD-lite": enough domain modeling to keep business logic clean, not so much
> that it slows new developers down.

## 2. Tech Stack

```
Runtime:        Python 3.11+
Server:         FastAPI + Uvicorn (ASGI)
Validation:     Pydantic v2
ORM:            SQLAlchemy 2.0 ORM
Database:       PostgreSQL 16 (async via asyncpg)
Migrations:     Alembic
Auth:           JWT (access + refresh tokens)
Testing:        pytest + pytest-asyncio + httpx
Observability:  structlog + prometheus-client + OpenTelemetry
Workers:        arq (async background jobs)
Linting:        ruff + mypy
```

### Why SQLAlchemy instead of SQLModel?

SQLModel is excellent for learning but abstracts away important ORM concepts.
This project intentionally uses pure SQLAlchemy to understand:

- Session lifecycle
- Transactions
- Unit of Work
- Relationship loading
- ORM vs domain separation

This gives stronger enterprise backend fundamentals.

Dependencies are declared in `pyproject.toml` (single source of truth). If a
`requirements.txt` is needed for deploy tooling, generate it from `pyproject`
rather than hand-maintaining it.

---

## 3. Folder Structure

```
async-pulse/
├── docs/
│   ├── architecture/
│   │   └── DESIGN.md
│   └── standards/
│       └── CODING_CONVENTIONS.md
│
├── src/
│   ├── main.py                    # App wiring only: register middleware,
│   │                              # exception handlers, routers, /health
│   │
│   ├── modules/                   # Feature slices — business logic lives here
│   │   ├── auth/
│   │   │   ├── router.py          # HTTP routes (thin: parse → service → respond)
│   │   │   ├── service.py         # Use-case logic, no fastapi imports
│   │   │   ├── repository.py      # Data access, returns domain entities
│   │   │   ├── entities.py        # Domain entity + business behavior
│   │   │   ├── schemas.py         # Pydantic request/response DTOs
│   │   │   ├── dependencies.py    # FastAPI Depends() wiring for this module
│   │   │   └── exceptions.py      # Domain exceptions (AuthError subclasses)
│   │   │
│   │   └── users/
│   │       ├── router.py
│   │       ├── service.py
│   │       ├── repository.py
│   │       ├── entities.py        # User domain entity
│   │       ├── models.py          # SQLAlchemy persistence model (UserModel)
│   │       ├── schemas.py
│   │       ├── dependencies.py
│   │       └── exceptions.py
│   │
│   ├── db/                        # SQLAlchemy plumbing only — no business logic
│   │   ├── base.py                # DeclarativeBase (all models import from here)
│   │   ├── session.py             # Async engine, session factory, get_async_session
│   │   ├── unit_of_work.py        # UnitOfWork class + get_unit_of_work dependency
│   │   └── registry.py            # Imports all models → target_metadata for Alembic
│   │
│   ├── core/                      # App-level technical plumbing — no business logic
│   │   ├── settings.py            # pydantic-settings (single source of config truth)
│   │   ├── lifespan.py            # Startup/shutdown (logging init, table creation)
│   │   ├── middleware.py          # CORS, request-id, access-log middleware
│   │   └── exception_handlers.py  # Domain exception → HTTP response (registered once)
│   │
│   ├── shared/                    # Reusable utilities — no framework, no DB imports
│   │   ├── security.py            # hash_password, verify_password, JWT encode/decode
│   │   ├── pagination.py          # PageParams, PagedResponse schemas
│   │   ├── exceptions.py          # AppError base + shared exception hierarchy
│   │   ├── constants.py           # Enums, string literals shared across modules
│   │   └── logger.py              # structlog configuration + get_logger()
│   │
│   └── workers/                   # Background jobs — arq only, no HTTP concerns
│       ├── tasks.py               # arq job function definitions
│       └── scheduler.py           # cron / periodic job registration
│
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── tests/
│   ├── conftest.py
│   ├── modules/
│   │   └── users/
│   │       ├── test_router.py
│   │       ├── test_service.py
│   │       └── test_repository.py
│   └── shared/
│
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

### Folder ownership rules

Each top-level folder has one job. If you're unsure where a file belongs, apply
these rules in order.

**`modules/`** — owns all business logic.

- A file belongs here if it's specific to one feature domain (users, auth, posts).
- Every module is a self-contained vertical slice: router → service → repository
  → entity → model → schemas → dependencies → exceptions.
- Modules may import from `shared/`, `db/`, and `core/`. They must **never**
  import from each other directly. Cross-module calls go through a service
  method, not a direct import.

**`db/`** — owns SQLAlchemy plumbing, nothing else.

- `base.py`: the `DeclarativeBase` that all `models.py` files inherit from.
- `session.py`: engine creation, `async_sessionmaker`, `get_async_session`.
- `unit_of_work.py`: `UnitOfWork` class and its FastAPI dependency.
- `registry.py`: imports every module's models so `Base.metadata` is complete for
  Alembic autogenerate (`target_metadata`). See §4.3.1.
- No business logic, no Pydantic schemas, no HTTP concerns.

**`core/`** — owns app-level technical wiring, nothing else.

- `settings.py`: all environment config via pydantic-settings. Single source of
  truth. No other file hardcodes env values.
- `lifespan.py`: startup (configure logging, create tables in dev) and shutdown.
- `middleware.py`: CORS, request-id header injection, access logging.
- `exception_handlers.py`: maps domain exceptions → HTTP responses. Registered
  once in `main.py`.
- No business logic, no DB queries, no domain exceptions defined here.

**`shared/`** — owns reusable utilities with zero framework or DB dependency.

- A file belongs here if it's used by two or more modules and contains no
  FastAPI, SQLAlchemy, or arq imports.
- `security.py`: password hashing and JWT encode/decode — pure functions.
- `pagination.py`: `PageParams` and `PagedResponse` — pure Pydantic.
- `exceptions.py`: `AppError` base class and the shared exception hierarchy that
  module exceptions extend.
- `constants.py`: enums and string literals shared across modules.
- `logger.py`: structlog configuration and a `get_logger()` factory.
- `metrics.py`: Prometheus counter/histogram definitions (added when needed).
- If a utility is only used by one module, put it in that module, not here.

**`workers/`** — owns background job definitions, nothing else.

- `tasks.py`: arq job functions. Each job is an async function that accepts a
  context dict and performs one unit of work.
- `scheduler.py`: cron / periodic job registration.
- Workers may import from `modules/` services and `db/` but have no HTTP
  concerns and never import from `core/`.

### Module file growth (flat first, promote when needed)

Module files are organized by **concern**, not by class. Default to flat files
and let each hold as many classes as its concern needs.

- `models.py` may define several SQLAlchemy models (`UserModel`, `ProfileModel`).
- `schemas.py` holds all the module's DTOs (`UserCreate`, `UserUpdate`, ...).
- `service.py` / `entities.py` / `repository.py` likewise hold one cohesive
  concern each, with as many classes as that concern requires.

Do **not** create a folder-per-concern up front. A `service/` folder containing a
single `service.py` is structure for a problem you don't have, and it adds an
`__init__.py` indirection a reader has to step through to find the code.

**Promotion rule.** When one file grows past ~300–400 lines, or holds 3+ cohesive
groups that don't belong together, convert *that one file* into a package — a
folder with `__init__.py` that re-exports the public names. Import paths stay
identical, so nothing downstream changes.

Before:

```
modules/users/
└── service.py
```

After (only this concern is promoted):

```
modules/users/
└── service/
    ├── __init__.py        # from .registration import RegistrationService
    │                      # from .profile import ProfileService
    ├── registration.py
    └── profile.py
```

Consumers still write `from src.modules.users.service import RegistrationService`.
The folder is an implementation detail; the public surface is unchanged.

Promote concerns independently — one module can have a flat `models.py` and a
promoted `service/` package at the same time. Only split what actually outgrew a
single file.

### Architecture flow

```
HTTP Request
  → core/middleware.py
    → modules/<feature>/router.py       (parse + validate)
      → modules/<feature>/service.py    (orchestrate, no fastapi imports)
        → modules/<feature>/entities.py (business invariants)
        → modules/<feature>/repository.py (data access, maps model ↔ entity)
          → db/unit_of_work.py          (transaction boundary)
            → db/session.py             (SQLAlchemy async session)
              → PostgreSQL
  ← core/exception_handlers.py         (domain exception → HTTP, on error)
```

Background jobs follow the same path from `workers/tasks.py` into services,
bypassing the HTTP layer entirely — which is why services must never import
`fastapi`.

---

## 4. User Module — Detailed Design

### 4.1 Persistence Model (SQLAlchemy 2.0)

The SQLAlchemy model represents **database persistence only**. Business behavior
lives on the domain entity (§4.4), not here.

```python
# src/modules/users/models.py

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(100), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

```python
# src/db/base.py

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base — all persistence models inherit from this."""
    pass
```

> Timestamps use DB-side defaults (`server_default`) and `onupdate`, so the
> database is the source of truth and `updated_at` refreshes automatically.

### 4.2 Pydantic Schemas (Request/Response DTOs)

```python
# src/modules/users/schemas.py

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# --- Request schemas ---

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=50)
    full_name: str | None = None
    is_active: bool | None = None


# --- Response schemas ---

class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}  # ORM mode


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
```

**Key difference from Zod:** Pydantic validates at the schema level. FastAPI
automatically:
- Parses the request body into the typed schema
- Returns 422 with detailed errors if validation fails
- Generates OpenAPI docs from the schemas

No manual `req.body()` parsing — it's all automatic.

### 4.3 Dependency Injection

AsyncPulse uses **manual dependency injection** — no runtime container. FastAPI's
`Depends()` *is* explicit DI: you write the factory functions and FastAPI runs the
chain per request. The composition for a feature lives in its `dependencies.py`
(the equivalent of a NestJS `*.module.ts` file).

```python
# src/modules/users/dependencies.py

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.settings import settings
from src.db.session import get_async_session
from src.db.unit_of_work import UnitOfWork, get_unit_of_work
from src.modules.users.entities import User
from src.modules.users.repository import UserRepository
from src.modules.users.service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# --- Composition: session → repository → service -------------------------

def get_user_repository(
    session: AsyncSession = Depends(get_async_session),
) -> UserRepository:
    """Construct a UserRepository for this request.

    Plain def/return — no yield, no cleanup needed. Reserve yield-dependencies
    for things with teardown (session, Redis connection, file handle).
    """
    return UserRepository(session)


def get_user_service(
    repo: UserRepository = Depends(get_user_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> UserService:
    """Compose the service from its dependencies (use keyword args, not positional)."""
    return UserService(repository=repo, uow=uow)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Extract and validate the current user from JWT. Returns a domain entity."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


# --- Annotated aliases: import these in routers --------------------------

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
```

Routers then consume the aliases, keeping signatures clean:

```python
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, service: UserServiceDep):
    return await service.get_user(user_id)
```

### 4.3.1 Dependency Injection Conventions

**Composition lives in `dependencies.py`.** Each module composes its own chain
(`session → repository → service`) there. Routers import the composed dependency
(or its `Annotated` alias); they never instantiate a repository or service
themselves. Infrastructure factories (`get_async_session`, `get_unit_of_work`)
live in `db/`, not in a module.

**Constructor style.** Wire services with **keyword arguments**
(`UserService(repository=repo, uow=uow)`), never positional — Python kwargs make
argument-ordering bugs impossible. If a constructor ever needs many collaborators,
group them into a small frozen dataclass rather than a long positional list.

**One-way layer direction.** Dependencies flow in a single direction and never
back:

```
Router → Service → Repository → UnitOfWork/Session
```

- Routers depend only on services (and request-scoped helpers like
  `get_current_user`). They must never query a repository directly.
- Services depend on repositories, the unit of work, and injected infrastructure
  (logger, mailer). They never import `fastapi` or anything from `core/`/routing.
- Repositories depend only on the session and persistence models. They never
  import a service or router.

**What to inject vs what not to inject.** Use constructor injection for
**stateful infrastructure** — things with a lifecycle, replaceable implementations,
or per-request state (repository, unit of work, mail client, cache client,
external API client). Do **not** inject loggers or metrics collectors; use a
module-level singleton instead:

```python
# idiomatic Python — not constructor injection
from src.shared.logger import get_logger

logger = get_logger(__name__)
```

This is the standard Python shop pattern. structlog's `capture_logs()` handles
the rare test that needs to assert on log output. Injecting loggers and metrics
via constructors is a Node/Java habit that adds constructor noise without a
practical benefit in Python.

**Cross-module rule (black-box isolation).** If module A needs data owned by
module B, A's service depends on **B's service** (via `get_b_service`), never on
`BRepository`. Reaching into another module's repository bypasses its validation,
business rules, and caching. Modules never import each other's repositories,
routers, or models directly.

**Public surface.** A module's `__init__.py` may re-export its service, entities,
and public types — never its router. Routers are aggregated separately by the API
router (§4.11) to avoid circular imports.

**Scope: singleton vs request-scoped.** Be deliberate about lifetime:

- *App singletons* (created once at import or in `lifespan`): `settings`, the
  SQLAlchemy `engine`, the arq pool, shared HTTP clients. These are module-level
  objects, **not** `Depends`.
- *Request-scoped* (via `Depends`): `session`, `repository`, `unit_of_work`,
  `service`, `current_user`. Stateful per request; must not leak across requests.

**Per-request cache contract.** FastAPI calls each dependency once per request and
caches the result. This is why `get_user_repository` and `get_unit_of_work` both
depending on `get_async_session` share the *same* session — the repository's
`flush` and the unit of work's `commit` act on one transaction. Do **not** create
a fresh session inside either factory; doing so silently splits the transaction.

**Central metadata registry (for Alembic).** Each module owns its own models, but
Alembic's autogenerate needs a single `MetaData` that sees every table. Import all
models into one registry module so `target_metadata` is complete:

```python
# src/db/registry.py — imported by alembic/env.py
from src.db.base import Base
from src.modules.users import models as _users_models  # noqa: F401
from src.modules.auth import models as _auth_models      # noqa: F401

target_metadata = Base.metadata
```

A repository querying its own module's tables imports them locally
(`from .models import UserModel`). If it must read another module's table, import
that table from this registry — never reach into the foreign module's `models.py`.

### 4.4 Domain Exceptions

Services raise these — never `HTTPException`. They're plain exceptions with no
FastAPI dependency, so the service layer stays reusable outside the web context.

```python
# src/modules/users/exceptions.py

from uuid import UUID


class UserError(Exception):
    """Base class for user-domain errors."""


class UserNotFound(UserError):
    def __init__(self, user_id: UUID):
        self.user_id = user_id
        super().__init__(f"User {user_id} not found")


class EmailAlreadyExists(UserError):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email already registered: {email}")


class UsernameAlreadyTaken(UserError):
    def __init__(self, username: str):
        self.username = username
        super().__init__(f"Username already taken: {username}")


class UserAlreadyInactive(UserError):
    def __init__(self, user_id: UUID):
        self.user_id = user_id
        super().__init__(f"User {user_id} is already inactive")
```

These are translated to HTTP responses once, centrally, in
`core/exception_handlers.py` (see §4.10).

### 4.5 Repository (Data Access)

The repository does **data access only** — no commits. It maps between the
SQLAlchemy persistence model (`UserModel`) and the domain entity (`User`), so the
rest of the app never touches raw ORM rows.

```python
# src/modules/users/repository.py

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.entities import User
from src.modules.users.models import UserModel


def _to_entity(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        username=row.username,
        hashed_password=row.hashed_password,
        full_name=row.full_name,
        is_active=row.is_active,
        is_superuser=row.is_superuser,
        created_at=row.created_at,
    )


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        row = await self.session.get(UserModel, user_id)
        return _to_entity(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None

    async def add(self, user: User) -> User:
        row = UserModel(
            id=user.id,
            email=user.email,
            username=user.username,
            hashed_password=user.hashed_password,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
        )
        self.session.add(row)
        # No commit here — the Unit of Work owns the transaction (§4.12).
        await self.session.flush()
        return _to_entity(row)

    async def persist(self, user: User) -> None:
        """Sync entity state back to its persistence row."""
        row = await self.session.get(UserModel, user.id)
        row.email = user.email
        row.username = user.username
        row.full_name = user.full_name
        row.is_active = user.is_active
        await self.session.flush()

    async def list_users(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[User], int]:
        total = await self.session.scalar(select(func.count(UserModel.id)))
        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(UserModel).offset(offset).limit(page_size)
        )
        rows = result.scalars().all()
        return [_to_entity(r) for r in rows], total or 0
```

> Pure SQLAlchemy 2.0: `select()` + `session.execute()` + `scalar_one_or_none()`
> / `scalars().all()`. The repository `flush`es but never `commit`s — commit is
> the Unit of Work's job (§4.12).

### 4.6 Domain Entities

SQLAlchemy models represent **database persistence**. Domain entities represent
**business behavior**. These are intentionally separate.

```python
# src/modules/users/entities.py

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.users.exceptions import UserAlreadyInactive
from src.shared.security import verify_password


@dataclass
class User:
    id: UUID
    email: str
    hashed_password: str
    username: str | None = None
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime | None = None

    def deactivate(self) -> None:
        if not self.is_active:
            raise UserAlreadyInactive(self.id)
        self.is_active = False

    def verify_password(self, password: str) -> bool:
        return verify_password(password, self.hashed_password)
```

Benefits:

- Prevent exposing raw ORM models
- Encapsulate business invariants
- Richer domain modeling
- Better service-layer design

This matches the Node entity pattern almost exactly.

### 4.7 Service Layer (Business Logic)

Application services orchestrate the use case: they call repositories, drive
domain-entity behavior, and own the transaction via the Unit of Work. No
`fastapi` import — failures raise domain exceptions.

```python
# src/modules/users/service.py

from uuid import UUID, uuid4

from src.db.unit_of_work import UnitOfWork
from src.modules.users.entities import User
from src.modules.users.exceptions import (
    EmailAlreadyExists,
    UsernameAlreadyTaken,
    UserNotFound,
)
from src.modules.users.repository import UserRepository
from src.modules.users.schemas import UserCreate, UserListResponse, UserUpdate
from src.shared.security import hash_password


class UserService:
    def __init__(self, repository: UserRepository, uow: UnitOfWork):
        self.repository = repository
        self.uow = uow

    async def get_user(self, user_id: UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise UserNotFound(user_id)
        return user

    async def create_user(self, data: UserCreate) -> User:
        if await self.repository.get_by_email(data.email):
            raise EmailAlreadyExists(data.email)
        if await self.repository.get_by_username(data.username):
            raise UsernameAlreadyTaken(data.username)

        user = User(
            id=uuid4(),
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
        )
        created = await self.repository.add(user)
        await self.uow.commit()
        return created

    async def update_user(self, user_id: UUID, data: UserUpdate) -> User:
        user = await self.get_user(user_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.repository.persist(user)
        await self.uow.commit()
        return user

    async def deactivate_user(self, user_id: UUID) -> None:
        user = await self.get_user(user_id)
        user.deactivate()  # domain invariant lives on the entity
        await self.repository.persist(user)
        await self.uow.commit()

    async def list_users(
        self, page: int = 1, page_size: int = 20
    ) -> UserListResponse:
        users, total = await self.repository.list_users(page, page_size)
        return UserListResponse(
            items=users, total=total, page=page, page_size=page_size
        )
```

### 4.8 Service Layer Rules

Application services coordinate use cases.

Responsibilities:

- Orchestrate repositories
- Apply business rules
- Coordinate transactions (via the Unit of Work)
- Use domain entities

Services **must remain framework-agnostic**.

Avoid:

```python
raise HTTPException(status_code=404)
```

Prefer:

```python
raise UserNotFound(user_id)
```

Exception translation happens in global handlers: **domain exception → HTTP
response** (§4.10). This keeps business logic reusable in:

- REST APIs
- Background jobs
- CLI tools
- Event consumers

### 4.9 Router (API Routes)

The module router uses a bare `/users` prefix. The `/api/v1` version prefix is
applied once by the aggregator (see §4.11), so bumping to v2 is a one-line change.
The service is injected via the `UserServiceDep` alias from `dependencies.py` —
the router defines no factories itself. Authorization is a reusable dependency,
not inline `if` checks.

```python
# src/modules/users/router.py

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from src.modules.users.dependencies import CurrentUserDep, UserServiceDep
from src.modules.users.entities import User
from src.modules.users.schemas import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=UserListResponse)
async def list_users(
    service: UserServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await service.list_users(page, page_size)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: CurrentUserDep):
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, service: UserServiceDep):
    return await service.get_user(user_id)


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(data: UserCreate, service: UserServiceDep):
    return await service.create_user(data)


def require_self_or_superuser(user_id: UUID, current_user: User) -> None:
    """Allow the owner or a superuser; otherwise 403."""
    if str(current_user.id) != str(user_id) and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: CurrentUserDep,
    service: UserServiceDep,
):
    require_self_or_superuser(user_id, current_user)
    return await service.update_user(user_id, data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    current_user: CurrentUserDep,
    service: UserServiceDep,
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")
    # Soft delete — the entity enforces the invariant.
    await service.deactivate_user(user_id)
```

### 4.10 Exception Handlers (Domain → HTTP)

Domain exceptions are mapped to HTTP responses in one place. Routers and
services stay clean; adding a new error is a new handler, not scattered `if`s.

```python
# src/core/exception_handlers.py

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.modules.users.exceptions import (
    EmailAlreadyExists,
    UsernameAlreadyTaken,
    UserAlreadyInactive,
    UserNotFound,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UserNotFound)
    async def _not_found(request: Request, exc: UserNotFound):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(EmailAlreadyExists)
    @app.exception_handler(UsernameAlreadyTaken)
    @app.exception_handler(UserAlreadyInactive)
    async def _conflict(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )
```

### 4.11 API Router Aggregator

```python
# src/api/router.py  (mounted from core/lifespan or main)

from fastapi import APIRouter

from src.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(users_router)
# Future modules mount here — version prefix is defined once.
```

### 4.12 Unit of Work

Repositories must **not** commit transactions — they perform data access only.
Transaction boundaries belong to the service, expressed through a Unit of Work.

```python
# src/db/unit_of_work.py

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session


class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def get_unit_of_work(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[UnitOfWork, None]:
    yield UnitOfWork(session)
```

Example multi-repository use case — both writes commit atomically:

```python
async def register_user(self, dto):
    user = await self.user_repo.add(...)
    await self.audit_repo.add(...)
    await self.uow.commit()   # one transaction, both writes
```

Benefits:

- Atomic operations
- Rollback support
- Multi-repository transactions
- Strong consistency

---

## 5. App Factory & Lifespan

```python
# src/main.py

from fastapi import FastAPI

from src.api.router import api_router
from src.core.exception_handlers import register_exception_handlers
from src.core.lifespan import lifespan
from src.core.middleware import register_middleware

app = FastAPI(
    title="AsyncPulse",
    version="0.1.0",
    lifespan=lifespan,
)

register_middleware(app)            # CORS, request-id, logging
register_exception_handlers(app)    # domain exception → HTTP
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health():
    """Liveness probe — used by Docker/compose healthchecks."""
    return {"status": "ok"}
```

```python
# src/core/lifespan.py

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.settings import settings
from src.db.session import create_db_and_tables
from src.shared.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: logging + tables (dev). Shutdown: cleanup."""
    configure_logging()
    if settings.ENV == "development":
        await create_db_and_tables()
    yield
    # Shutdown: close pool, flush traces, etc.
```

---

## 6. Database Setup (Async SQLAlchemy)

```python
# src/db/session.py

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.settings import settings
from src.db.base import Base

engine = create_async_engine(
    settings.DATABASE_URL,  # postgresql+asyncpg://...
    echo=settings.ENV == "development",
    pool_size=20,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def create_db_and_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Session per request. Rolls back on error; commit is owned by the UoW.

    Repositories only add/flush — transaction control lives in the Unit of Work
    (§4.12), so a single request is one atomic unit across repository calls.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

---

## 7. Config (Pydantic Settings)

```python
# src/core/settings.py

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"
    # No default — must be provided via env. App fails loudly at startup if unset.
    SECRET_KEY: str
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/asyncpulse"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_weak_secret(cls, v: str, info) -> str:
        # Guard against shipping a placeholder secret to a real environment.
        if info.data.get("ENV") != "development" and v in {"", "change-me", "change-me-in-production"}:
            raise ValueError("SECRET_KEY must be set to a strong value outside development")
        return v


settings = Settings()
```

> `SECRET_KEY` has no default. In non-dev environments a missing or placeholder
> value raises at startup rather than silently weakening token security.

---

## 8. Test Fixtures

```python
# tests/conftest.py

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.db.base import Base
from src.db.session import get_async_session
from src.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/asyncpulse_test"


@pytest_asyncio.fixture
async def test_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(test_session: AsyncSession):
    async def override_session():
        yield test_session

    app.dependency_overrides[get_async_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
```

---

## 9. Key Async Patterns to Internalize

### The `async/await` chain

Every DB call, every external HTTP call, every file I/O is `await`-able:

```python
# This is the core pattern — everything downstream must be async
@router.get("/{user_id}")
async def get_user(user_id: UUID, ...):
    user = await service.get_user(user_id)        # async
    # Inside service:
    #   user = await repository.get_by_id(user_id)    # async
    #     row = await session.execute(select(...))     # async
    return user
```

If you forget `await`, you get a coroutine object instead of the actual result.
FastAPI will return an empty response — silent failure, not an error. Watch for
this.

### Dependency injection via function signatures

```python
# NestJS:
#   @Injectable()
#   class UserService {
#     constructor(private repo: UserRepository) {}
#   }

# FastAPI: just type-hint it
async def get_user(
    user_id: UUID,
    service: UserService = Depends(get_user_service),  # auto-injected
):
    return await service.get_user(user_id)
```

### Parallel async operations

```python
import asyncio

# Run multiple independent queries concurrently
users_task = repo.list_users()
posts_task = post_repo.list_posts()
users, posts = await asyncio.gather(users_task, posts_task)
```

---

## 10. Docker Compose (Dev Environment)

```yaml
# docker-compose.yml

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: asyncpulse
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  api:
    build: .
    command: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/asyncpulse
    depends_on:
      - db

volumes:
  pgdata:
```

---

## 11. Observability

Production systems need visibility. Three pillars:

### Logging

Structured application logs via **structlog** (configured in `shared/logger.py`,
initialized in `core/lifespan.py`).

```python
logger.info("user_registered", user_id=str(user.id))
```

### Metrics

Track request latency, error rate, database latency, and active sessions via
**prometheus-client** (collectors in `shared/metrics.py`), scraped by Prometheus.

### Tracing

Distributed tracing for bottlenecks via **OpenTelemetry** (FastAPI + SQLAlchemy
instrumentation), exported to your collector of choice.

---

## 12. Background Jobs

Not all work belongs in the request/response cycle. Examples:

- Email delivery
- Notifications
- Webhooks
- Report generation
- Retry workflows

Recommended worker: **arq** (async, Redis-backed). Job definitions live in
`workers/tasks.py`, scheduled jobs in `workers/scheduler.py`.

Flow:

```
Request
  → Persist data
    → Enqueue job
      → Return response
```

Benefits:

- Lower latency
- Better reliability
- Improved scalability

---

## 13. Development Roadmap

```
Phase 1: Foundation (current)
  [x] Design doc (this file)
  [ ] Project scaffold (pyproject.toml, Dockerfile, docker-compose)
  [ ] Reconcile scaffold to modules/ layout; align pyproject (py3.11+, ruff)
  [ ] db/ setup: Base, async session, Unit of Work
  [ ] User persistence model + domain entity + migration
  [ ] Domain exceptions + central handlers (core/exception_handlers.py)
  [ ] CRUD routes (list, get, create, update, soft-delete)
  [ ] Tests for all routes

Phase 2: Auth
  [ ] JWT access + refresh token flow
  [ ] Login / logout endpoints
  [ ] Password reset flow
  [ ] Role-based access control

Phase 3: Expand
  [ ] Second module (posts, notifications, whatever)
  [ ] Extract shared/BaseRepository[Model] once a 2nd module shows the pattern
  [ ] WebSocket support
  [ ] Rate limiting
  [ ] API key auth

Phase 4: Production Hardening
  [ ] Structured logging (structlog)
  [ ] Prometheus metrics
  [ ] OpenTelemetry tracing
  [ ] Background workers (arq)
  [ ] Redis caching
```
