# Coding Style & Architecture Conventions

This document describes the coding style, architectural patterns, and conventions
used in this project to ensure consistency, maintainability, and scalability. It
codifies the design in `../architecture/DESIGN.md` into day-to-day rules and follows the most
widely adopted Python standards — [PEP 8](https://peps.python.org/pep-0008/),
[PEP 257](https://peps.python.org/pep-0257/) (docstrings), and
[PEP 484](https://peps.python.org/pep-0484/) (type hints) — enforced by `ruff`
and `pyright`.

---

## 1. Project Architecture

The project is a **feature-first modular monolith** with layered internals. Each
request flows in one direction through the layers.

```
HTTP Request
  ↓
Middleware (CORS, request-id, access logging)
  ↓
Router          (parse + validate, FastAPI concerns only)
  ↓
Service         (use-case orchestration, business logic)
  ├── Domain Entity   (business invariants / behavior)
  ├── Repository      (data access; maps model ↔ entity)
  │     ↓
  │   SQLAlchemy ORM → PostgreSQL
  └── Unit of Work    (transaction boundary — commit / rollback)
```

The Unit of Work is **not** downstream of the repository. Both the repository and
the Unit of Work are collaborators of the service — the service drives data access
through the repository and controls the transaction boundary through the Unit of
Work independently.

Each layer has a single responsibility.

| Layer         | Responsibility                                              |
| ------------- | ----------------------------------------------------------- |
| Middleware    | CORS, request-id injection, access logging, preprocessing   |
| Router        | Parse/validate HTTP request, call service, shape response   |
| Service       | Use-case orchestration and business logic (framework-free)  |
| Domain Entity | Business invariants and behavior, separate from persistence |
| Repository    | Database queries; maps persistence model ↔ domain entity    |
| Unit of Work  | Transaction boundary (commit / rollback) — sibling to repo  |

The validation, response-modeling, and exception-translation concerns are handled
declaratively by FastAPI + Pydantic and by central exception handlers rather than
by hand-written middleware.

---

## 2. Feature-Based Module Structure

Code is organized by **feature module** (vertical slice), not by technical layer.
Each module is a self-contained slice that owns its router, service, repository,
entities, persistence models, schemas, dependencies, and exceptions.

Example structure:

```
src/modules/users/
│
├── router.py          # HTTP routes (thin: parse → service → respond)
├── service.py         # Use-case logic, no fastapi imports
├── repository.py      # Data access, returns domain entities
├── entities.py        # Domain entity + business behavior
├── models.py          # SQLAlchemy persistence model (UserModel)
├── schemas.py         # Pydantic request/response DTOs
├── dependencies.py    # FastAPI Depends() wiring for this module
├── exceptions.py      # Domain exceptions (UserError subclasses)
└── __init__.py        # Public surface (re-exports service/entities/types)
```

The **auth module** promotes its single `dependencies.py` into three focused files
because authentication and authorization are genuinely distinct concerns:

```
modules/auth/dependencies/
├── __init__.py       # Re-exports all dependencies, authentication, and permissions
├── providers.py      # DI wiring only: get_auth_repository, get_auth_service
├── authentication.py # Auth gate: oauth2_scheme, get_current_user, CurrentUserDep
└── permissions.py    # RBAC guards: require_role, AdminDep, SuperuserDep
```

Other modules import the gate/guards from the auth module root facade:

```python
from src.modules.auth import get_current_user, CurrentUserDep, require_role, SuperuserDep
```

Each module is self-contained and manages its own dependencies.

### Flat first, promote when needed

Module files are organized by **concern**, not by class. Default to flat files and
let each hold as many classes as its concern needs (`models.py` may define
`UserModel` and `ProfileModel`; `schemas.py` holds all the module's DTOs).

Do **not** create a folder-per-concern up front. **Promote when cohesion drops,
not when line count alone grows.** A 500-line service file that handles one
tightly related concern is fine; a 150-line file mixing three unrelated concerns
is not. Line count (~300–400 lines) is a _signal_ to re-examine cohesion, not an
automatic trigger. When a file genuinely holds 3+ groups that don't belong
together, promote _that one file_ into a package — a folder with `__init__.py`
that re-exports the public names. Import paths stay identical, so nothing
downstream changes.

```
# before                    # after (only this concern promoted)
modules/users/              modules/users/
└── service.py              └── service/
                                ├── __init__.py   # re-exports public names
                                ├── registration.py
                                └── profile.py
```

Consumers still write `from src.modules.users.service import RegistrationService`.

---

## 3. Dependency Injection (FastAPI `Depends`)

The project uses **manual dependency injection** — no runtime container. FastAPI's
`Depends()` _is_ explicit DI: you write the factory functions, FastAPI runs the
chain per request and caches each result for the request's lifetime. The
composition for a feature lives in its `dependencies.py` (the equivalent of a
NestJS `*.module.ts` file).

### Composition lives in `dependencies.py`

Each module composes its own chain (`session → repository → service`) there.
Infrastructure factories (`get_async_session`, `get_unit_of_work`) live in `db/`,
not in a module.

```python
# src/modules/users/dependencies.py
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.db.unit_of_work import UnitOfWork, get_unit_of_work
from src.modules.users.repository import UserRepository
from src.modules.users.service import UserService


def get_user_repository(
    session: AsyncSession = Depends(get_async_session),
) -> UserRepository:
    return UserRepository(session)


def get_user_service(
    repo: UserRepository = Depends(get_user_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> UserService:
    # Keyword args, never positional — see "Constructor style" below.
    return UserService(repository=repo, uow=uow)


# Annotated aliases — import these in routers to keep signatures clean.
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
```

Routers consume the alias; they never instantiate a repository or service
themselves:

```python
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, service: UserServiceDep):
    return await service.get_user(user_id)
```

### Constructor style — keyword args, group when many

Wire services with **keyword arguments** (`UserService(repository=repo, uow=uow)`),
never positional. Python kwargs make argument-ordering bugs impossible, which is
the idiomatic equivalent of the Node "options object" rule.

- **1–2 dependencies:** keyword arguments are sufficient
  (`UserService(repository=repo, uow=uow)`).
- **3+ dependencies:** group collaborators into a small frozen dataclass rather
  than a long argument list.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class UserServiceDeps:
    repository: UserRepository
    uow: UnitOfWork
    mailer: MailClient
```

### What to inject vs what not to inject

Use constructor injection for **stateful infrastructure** — things with a
lifecycle, replaceable implementations, or per-request state (repository, unit of
work, mail/cache/external-API client).

Do **not** inject loggers or metrics collectors. Use a module-level singleton —
this is the idiomatic Python pattern and avoids constructor noise:

```python
from src.shared.logger import get_logger

logger = get_logger(__name__)
```

### Scope: singleton vs request-scoped

- **App singletons** (created once at import or in `lifespan`): `settings`, the
  SQLAlchemy `engine`, the arq pool, shared HTTP clients. These are module-level
  objects, _not_ `Depends`.
- **Request-scoped** (via `Depends`): `session`, `repository`, `unit_of_work`,
  `service`, `current_user`. Stateful per request; must not leak across requests.

### Use `yield` only when there is teardown

Plain `def`/`return` factories are the default. Reserve `yield`-dependencies for
resources with cleanup (session, Redis connection, file handle).

### Per-request cache contract

FastAPI calls each dependency once per request and caches the result. This is why
`get_user_repository` and `get_unit_of_work` both depending on
`get_async_session` share the _same_ session — the repository's `flush` and the
unit of work's `commit` act on one transaction. Never create a fresh session
inside a factory; doing so silently splits the transaction.

---

## 4. Routers

Routers stay **thin** and handle HTTP concerns only.

Responsibilities:

- Receive request data (validated automatically by Pydantic schemas)
- Call the injected service
- Declare `response_model` so persistence fields never leak

```python
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, service: UserServiceDep):
    return await service.create_user(data)
```

Routers must not contain business logic. Module routers use a **bare prefix**
(`/users`); the `/api/v1` version prefix is applied once by the API aggregator
(§4.1), so a version bump is a one-line change.

Authorization is a **reusable dependency or helper**, not scattered inline `if`
checks:

```python
def require_self_or_superuser(user_id: UUID, current_user: User) -> None:
    if str(current_user.id) != str(user_id) and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")
```

> `HTTPException` is acceptable in the router/dependency layer (it _is_ the HTTP
> layer). It must never appear in services — raise a domain exception there and
> let the central handler in §11 translate it to HTTP.

### 4.1 API Aggregation

Module routers are **never imported by `main.py` directly**, and a module's
`__init__.py` never re-exports its router (routers carry wiring side-effects;
importing them eagerly invites circular imports). Instead, a single aggregator
collects every module router, applies the `/api/v1` version prefix **once**, and
exposes one `api_router` that `main.py` includes.

```python
# src/api/router.py — the one place version + module routers are joined
from fastapi import APIRouter

from src.modules.users.router import router as users_router
from src.modules.auth.router import router as auth_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(users_router)   # bare prefix "/users" → "/api/v1/users"
api_router.include_router(auth_router)
```

```python
# src/main.py
app.include_router(api_router)
```

Because the version prefix lives here and module routers stay version-agnostic
(`/users`, not `/api/v1/users`), bumping to `v2` is a one-line change in the
aggregator. This is the only module-crossing import of a router in the codebase.

---

## 5. Services

Services contain business logic and orchestrate the use case: they call
repositories, drive domain-entity behavior, and own the transaction via the Unit
of Work.

```python
async def create_user(self, data: UserCreate) -> User:
    if await self.repository.get_by_email(data.email):
        raise EmailAlreadyExists(data.email)
    user = User(id=uuid4(), email=data.email, ...)
    created = await self.repository.add(user)
    await self.uow.commit()   # service owns the transaction boundary
    return created
```

Services should:

- Be **framework-agnostic** — no `fastapi` import, no `HTTPException`
- Raise **domain exceptions** (`UserNotFound`), never HTTP errors
- Be easily unit-testable
- Remain reusable from REST routes, background jobs, CLI tools, and event
  consumers

This is why services never import `fastapi`: a background worker drives the same
service without an HTTP layer.

**Common anti-patterns:**

```python
# ❌ HTTP exception in a service — breaks reusability outside the web context
async def get_user(self, user_id: UUID) -> User:
    user = await self.repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# ✅ Domain exception — translated to HTTP once, centrally (§11)
async def get_user(self, user_id: UUID) -> User:
    user = await self.repository.get_by_id(user_id)
    if not user:
        raise UserNotFound(user_id)
    return user
```

```python
# ❌ Service commits directly — bypasses the Unit of Work contract
async def create_user(self, data: UserCreate) -> User:
    created = await self.repository.add(user)
    await self.session.commit()   # wrong — session leaked into the service
    return created

# ✅ Service delegates the transaction boundary to the Unit of Work
async def create_user(self, data: UserCreate) -> User:
    created = await self.repository.add(user)
    await self.uow.commit()
    return created
```

---

## 6. Repositories

Repositories perform **data access only** — no commits. They map between the
SQLAlchemy persistence model (`UserModel`) and the domain entity (`User`) so the
rest of the app never touches raw ORM rows.

```python
async def add(self, user: User) -> User:
    row = UserModel(id=user.id, email=user.email, ...)
    self.session.add(row)
    await self.session.flush()   # flush, never commit — the UoW owns the txn
    return _to_entity(row)
```

Responsibilities:

- Contain database queries (pure SQLAlchemy 2.0: `select()` + `session.execute()`
  - `scalar_one_or_none()` / `scalars().all()`)
- Map model ↔ domain entity
- `flush` but **never** `commit` (the Unit of Work owns transactions, §12)
- No business logic

**Common anti-pattern:**

```python
# ❌ Repository commits — steals the transaction from the Unit of Work;
#    multi-repository atomic writes become impossible
async def add(self, user: User) -> User:
    self.session.add(row)
    await self.session.commit()   # wrong

# ✅ Flush only — the service calls uow.commit() after all writes are done
async def add(self, user: User) -> User:
    self.session.add(row)
    await self.session.flush()
    return _to_entity(row)
```

### Separation of Persistence Models, Domain Entities, and Read Projections

Keep three concerns distinct:

1. **Persistence model (`UserModel`):** the SQLAlchemy table mapping in
   `models.py`. Database structure only — no business behavior.
2. **Domain entity (`User`):** business behavior and invariants in `entities.py`
   (e.g. `deactivate()`). Entity retrieval (`get_by_id`) must be **join-free** and
   return only the raw entity mapping. Used for write paths, state validation, and
   update cycles.
3. **Read projections (`UserWithDisplay` / `Details`):** a read-model tailored for
   delivery (joined/aggregated fields). Repository methods returning projections
   must be explicitly named (e.g. `get_user_details_by_id(id)`). Used for GET
   endpoints and response shaping.

Never pollute the domain entity with read-only joined fields (`role_name`,
`team_label`). Keep them in separate projection types.

---

## 7. Request Validation (Pydantic v2)

All request validation is handled by **Pydantic v2 schemas**. FastAPI parses the
body into the typed schema, returns `422` with detailed errors on failure, and
generates OpenAPI docs automatically — there is no manual body parsing.

Prefer Pydantic's purpose-built field types over loose strings for clarity and
correct validation:

- Use `EmailStr` instead of a plain `str` for emails.
- Use `UUID` (from `uuid`) for identifiers.
- Use `Field(...)` for constraints (`min_length`, `max_length`, `ge`, `le`).

```python
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None
```

Routers receive validated data only — the schema type _is_ the validation
contract.

---

## 8. Schema-Driven Typing (No Duplicate DTOs)

Pydantic schemas are the single source of typing for the request/response
boundary — the Python equivalent of the Node `TypedRequest` pattern. The router
parameter's type annotation drives parsing, validation, and editor inference at
once:

```python
async def create_user(data: UserCreate, service: UserServiceDep):
    ...   # `data` is fully typed and already validated
```

Benefits:

- Schema-driven typing
- No duplicate DTO definitions
- Auto-generated OpenAPI documentation
- Strong static typing under `pyright`

---

## 9. DTOs & Service Input Contracts

Pydantic schemas (`schemas.py`) are the strict payload boundary between the
delivery layer (routers) and the domain layer (services).

### Response schemas use ORM mode and a response_model firewall

Response schemas enable `from_attributes` so a domain entity / ORM row can be
serialized directly, and the router's `response_model` guarantees only declared
fields are emitted:

```python
class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}  # ORM mode
```

> Always set `response_model`. It is the firewall that prevents persistence-only
> fields like `hashed_password` from ever leaking into a response.

### Services dictate their own input contracts

Services should not bind directly to HTTP request schemas where internal fields
are needed. A service may accept the schema as-is initially, then evolve its own
input type so the domain layer doesn't break when the HTTP schema changes and so
internal fields (e.g. `ip_address`) never appear in the client payload.

```python
# Accept the schema directly when they match…
async def create_user(self, data: UserCreate) -> User: ...

# …or define an explicit input dataclass when internal fields are needed.
@dataclass(frozen=True)
class RegisterUserInput:
    email: str
    username: str
    password: str
    ip_address: str | None = None   # internal, never in the HTTP schema
```

---

## 10. API Response Standard

FastAPI serializes the returned object through the route's `response_model`. The
**default success contract is the typed response schema itself** — no manual
envelope is added, which keeps responses idiomatic and OpenAPI-accurate.

```python
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, service: UserServiceDep):
    return await service.get_user(user_id)   # serialized as UserResponse
```

Collections use an explicit paginated schema rather than a bare list, so metadata
travels with the data:

```python
class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
```

Error responses follow FastAPI's `{"detail": ...}` convention, produced centrally
by the exception handlers (§11).

---

## 11. Error Handling

Errors use **custom domain exception classes**, defined per module in
`exceptions.py`, rooted in a shared `AppError` base (`shared/exceptions.py`).

```python
class UserError(Exception):
    """Base class for user-domain errors."""

class UserNotFound(UserError):
    def __init__(self, user_id: UUID):
        self.user_id = user_id
        super().__init__(f"User {user_id} not found")
```

Rules:

- Services and entities **raise** domain exceptions; they never handle them and
  never raise `HTTPException`.
- Domain exceptions are translated to HTTP responses in **one place**,
  `core/exception_handlers.py`, registered once in `main.py`. Adding a new error
  is a new handler, not scattered `if`s.

```python
# src/core/exception_handlers.py
def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UserNotFound)
    async def _not_found(request: Request, exc: UserNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})
```

Prefer `raise UserNotFound(user_id)` over `raise HTTPException(status_code=404)`.
This keeps business logic reusable outside the web context.

---

## 12. Layer Dependency Rules

Dependencies flow in a single direction and never back:

```
Router → Service → Repository → UnitOfWork / Session
```

- **Routers** depend only on services (and request-scoped helpers like
  `get_current_user`). They must never query a repository directly.
- **Services** depend on repositories, the unit of work, and injected
  infrastructure. They never import `fastapi` or anything from `core/` / routing.
- **Repositories** depend only on the session and persistence models. They never
  import a service or router, and never `commit`.

This prevents architectural drift.

### Cross-Module Communication (black-box isolation)

Modules are strictly encapsulated black boxes.

- If module A needs data owned by module B, **A's service depends on B's service**
  (via `get_b_service`), never on `BRepository`. Reaching into another module's
  repository bypasses its validation, business rules, and caching.
- Modules never import each other's repositories, routers, or models directly.
- A module's `__init__.py` may re-export its service, entities, and public types —
  **never its router**. Routers are aggregated separately (§4.1) to
  avoid circular imports.

### Transactions belong to the Unit of Work

Repositories do data access only; the service owns the transaction boundary
through the Unit of Work, enabling atomic multi-repository writes:

```python
async def register_user(self, dto):
    user = await self.user_repo.add(...)
    await self.audit_repo.add(...)
    await self.uow.commit()   # one transaction, both writes
```

---

## 13. Naming Conventions

Follow PEP 8: `snake_case` for modules, functions, and variables;
`PascalCase` for classes; `UPPER_SNAKE_CASE` for constants.

| Component             | Convention                                                 |
| --------------------- | ---------------------------------------------------------- |
| Module files          | `service.py`, `repository.py`, `router.py`                 |
| Packages / folders    | `users/`, `auth/` (lowercase, singular noun)               |
| Classes               | `UserService`, `UserRepository`                            |
| Persistence models    | `UserModel` (suffix `Model`)                               |
| Domain entities       | `User` (no suffix)                                         |
| Read projections      | `UserDetails`, `UserWithDisplay` (descriptive noun suffix) |
| Request/response DTOs | `UserCreate`, `UserUpdate`, `UserResponse`                 |
| Domain exceptions     | `UserNotFound`, `EmailAlreadyExists`                       |
| Dependency factories  | `get_user_service`, `get_user_repository`                  |
| `Annotated` aliases   | `UserServiceDep`, `CurrentUserDep`                         |
| Functions / vars      | `snake_case`                                               |
| Constants             | `ACCESS_TOKEN_EXPIRE_MINUTES`                              |

Because the layer is conveyed by the _file_ (`service.py`) inside a feature
folder, class names don't repeat the folder (`users/service.py → UserService`,
not `UsersUserService`).

---

## 14. Docstrings (PEP 257)

Every module and public class/function should have a concise docstring. Match
density to the layer — high-signal, never ceremonial.

- **Module docstring:** one line stating the module's role.
  ```python
  """User feature slice — HTTP routes (thin: parse → service → respond)."""
  ```
- **Routers:** one line per route handler, high-level intent only.
  `"""Authenticate user and issue tokens."""`
- **Services:** docstring only for non-obvious business logic.
  `"""Rotate tokens by atomically consuming the old session and creating a new one."""`
- **Repositories:** minimal docs, only for complex or multi-step queries.
  `"""Atomically mark the session revoked and return it if it was active."""`
- **Entities:** document invariants that aren't obvious from the method name.

Use the imperative mood ("Return the user", not "Returns the user"), per PEP 257.
Do not restate type information already expressed by annotations.

---

## 15. Imports & Module Public Surface

### Import ordering (PEP 8, enforced by ruff/isort)

Three groups, each alphabetized, separated by a blank line:

1. Standard library
2. Third-party
3. First-party (`src...`)

```python
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.db.session import get_async_session
from src.modules.users.service import UserService
```

### Import style rules

1. **Absolute imports** rooted at `src.` for anything cross-package. Relative
   imports are acceptable only _within the same module_ for closely related files.
2. **No wildcard imports** (`from x import *`) outside a deliberate package
   `__init__.py` re-export.
3. **No default-export equivalents.** Python has none; export named symbols and
   import them explicitly (`from .service import UserService`).

### Own-module vs cross-module models

- **Own module models:** import relatively within the module.
  ```python
  from .models import UserModel
  ```
- **Cross-module tables:** a repository that must read another module's table
  imports it from the **central registry**, never by reaching into the foreign
  module's `models.py`.
  ```python
  from src.db.registry import users   # ✅ central
  # from src.modules.users.models import UserModel   # ❌ reaching in
  ```

### Module public surface (`__init__.py`)

A module's `__init__.py` is its public API. It may re-export the service,
entities, and public types — **never the router** (routers carry wiring
side-effects and are aggregated by the API router, §4.1, to avoid circular
imports).

```python
# src/modules/users/__init__.py  — ✅
from .entities import User
from .service import UserService

# ❌ never re-export the router from a module's __init__
# from .router import router
```

### Central metadata registry (Alembic)

Each module owns its models, but Alembic autogenerate needs a single `MetaData`
that sees every table. Import all models into `src/db/registry.py` so
`target_metadata` is complete (`# noqa: F401` on the side-effect imports).

---

## 16. Logging

The project treats logging as a cross-cutting concern using **structlog**,
configured once in `shared/logger.py` and initialized in `core/lifespan.py`.

Unlike the Node convention, loggers are **not** dependency-injected. Use a
module-level singleton — the idiomatic Python pattern across all layers:

```python
from src.shared.logger import get_logger

logger = get_logger(__name__)

logger.info("user_registered", user_id=str(user.id))
```

Emit **structured, event-style logs** (an event name plus key/value context),
not interpolated sentences. Tests that need to assert on output use structlog's
`capture_logs()` rather than a mock logger.

---

## 17. Metrics & Tracing

Observability beyond logs uses **prometheus-client** for metrics and
**OpenTelemetry** for distributed tracing, both configured once and used as
module-level singletons — the same pattern as logging (§16).

### Metrics (Prometheus)

Define counters, histograms, and gauges in `shared/metrics.py`. Never define
metric objects inline inside a function — module-level singletons ensure the
Prometheus registry sees each metric exactly once.

```python
# src/shared/metrics.py
from prometheus_client import Counter, Histogram

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

request_duration_seconds = Histogram(
    "request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
)
```

Import and update at the call site — no injection needed:

```python
from src.shared.metrics import http_requests_total

http_requests_total.labels(method="POST", path="/users", status_code=201).inc()
```

Expose the `/metrics` endpoint via the `prometheus_client` ASGI middleware
registered in `core/middleware.py`, not as a regular FastAPI route.

### Tracing (OpenTelemetry)

Configure the OTel SDK once in `core/lifespan.py` (startup). Use the zero-code
auto-instrumentation packages for FastAPI and SQLAlchemy so spans are emitted
automatically without decorating every function:

```python
# core/lifespan.py (startup)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)
```

For manual spans in business-critical paths, obtain a tracer as a module-level
singleton — **not** via constructor injection:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def some_service_method(self) -> None:
    with tracer.start_as_current_span("some_service_method"):
        ...
```

### What not to do

```python
# ❌ Metric defined inside a function — re-registers on every call, raises error
async def create_user(self, data):
    counter = Counter("users_created", "...")   # wrong
    counter.inc()

# ❌ Tracer injected via constructor — unnecessary noise, no practical benefit
class UserService:
    def __init__(self, repo, uow, tracer):   # wrong
        self.tracer = tracer
```

---

## 18. Testing Strategy

Tests use **pytest + pytest-asyncio + httpx**, mirroring the module layout under
`tests/modules/<feature>/`.

### Repository tests

Exercise data access against a real test database session.

```
tests/modules/users/test_repository.py
```

### Service unit tests

Test business logic with a fake or in-memory repository; assert that domain
exceptions are raised.

```
tests/modules/users/test_service.py
```

### Integration / router tests

Use httpx `AsyncClient` over the ASGI app to test the full path
`router → service → repository`, with `get_async_session` overridden via
`app.dependency_overrides`.

```
tests/modules/users/test_router.py
```

Async tests must be `async def` and awaited; shared fixtures (test engine,
session, client) live in `tests/conftest.py`.

---

## 19. Code Style & Tooling (PEP 8 + PEP 484)

Style is enforced automatically — `ruff` for linting/formatting/import-sorting and
`pyright` in strict mode for typing. Run them before committing.

- **Line length:** follow the configured limit (88, Black/ruff default).
- **Indentation:** 4 spaces, never tabs.
- **Type hints everywhere.** All function signatures are fully annotated. Use
  modern built-in generics and unions: `list[User]`, `dict[str, int]`,
  `str | None` (not `List`, `Dict`, or `Optional` in new code).
- **`async def` end to end.** Every DB call, external HTTP call, and file I/O is
  awaited. A forgotten `await` yields a coroutine object and a silent empty
  response — watch for it.
- **Use `asyncio.gather`** for independent concurrent awaits, not sequential
  awaits.
- **No mutable default arguments** (`def f(x: list = [])` is a bug); use `None`
  and construct inside.
- **f-strings** for interpolation; never `%` or `.format()` in new code.
- **Configuration via `pydantic-settings` only.** No module hardcodes env values;
  `settings` is the single source of truth and fails loudly at startup if a
  required secret is unset.

---

## 20. Core Principles

- Single Responsibility per layer and per module file
- Explicit dependencies (manual DI via `Depends`, keyword-wired constructors)
- Feature-first modular design with black-box module isolation
- Schema-first validation (Pydantic) and `response_model` firewalls
- Thin routers, framework-agnostic services
- Domain exceptions over HTTP exceptions in business logic
- Persistence model ≠ domain entity ≠ read projection
- Repositories never commit — the Unit of Work owns transactions
- Fully typed, async end to end, automatically linted

---

## Summary

Key architectural decisions:

- Feature-first modular monolith with one-way layering
  (router → service → { entity, repository, unit of work })
- Manual dependency injection via FastAPI `Depends`, composed in `dependencies.py`
- Pydantic v2 for validation, typing, and OpenAPI — no duplicate DTOs
- Domain exceptions translated to HTTP once, centrally
- Domain entities separate from persistence models and read projections
- Unit of Work owns transaction boundaries; repositories only flush
- Structured logging (structlog), metrics (prometheus-client), and tracing (OTel)
  all use module-level singletons — never constructor-injected
- PEP 8 / PEP 257 / PEP 484 enforced by `ruff` + `pyright`

These conventions keep the codebase scalable, maintainable, and easy to onboard
into.
