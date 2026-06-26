# AI Agent Developer Guide (`AGENTS.md`)

Welcome, AI Agent! This document is your onboarding guide to the **AsyncPulse** codebase. It outlines the architecture, design patterns, coding conventions, and workflow rules that you must strictly adhere to when modifying or extending this repository.

Before working on the codebase, please review the core documentation files in the `docs` directory:

- **System Architecture & Design**: [DESIGN.md](file:///Users/kartikranjan/Desktop/Python/async-pulse/docs/architecture/DESIGN.md)
- **Coding Style & Conventions**: [CODING_CONVENTIONS.md](file:///Users/kartikranjan/Desktop/Python/async-pulse/docs/standards/CODING_CONVENTIONS.md)

---

## 1. System Overview & Tech Stack

AsyncPulse is an asynchronous Python REST API built as a learning bridge from NestJS/TypeScript to modern Python backend development.

- **Framework**: FastAPI (runs on Uvicorn ASGI server)
- **Validation**: Pydantic v2 (replaces Zod / class-validator)
- **ORM**: SQLAlchemy 2.0 (pure ORM, **not** SQLModel)
- **Database**: PostgreSQL 16 (accessed asynchronously via `asyncpg` driver)
- **Migrations**: Alembic
- **Background Jobs**: `arq` (Redis-backed async worker queue)
- **Observability**: `structlog` (structured logging) + `prometheus-client` (metrics) + OpenTelemetry (tracing)
- **Testing**: `pytest` + `pytest-asyncio` + `httpx`

---

## 2. Directory Layout & Feature Modularization

The codebase is organized as a **feature-first modular monolith**. All business logic lives inside self-contained feature slices under `src/modules/`.

```text
src/
├── main.py                      # App initialization, middleware, routes aggregation
├── api/
│   └── router.py                # Aggregator for versioned module routers
├── modules/                     # Feature slices (vertical slices)
│   ├── auth/
│   └── users/
│       ├── router.py            # Thin HTTP layer (FastAPI router)
│       ├── service.py           # Use-case logic (framework-free)
│       ├── repository.py        # Data access layer (maps persistence model ↔ entity)
│       ├── entities.py          # Domain entity representing business behavior/invariants
│       ├── models.py            # SQLAlchemy persistence model (e.g., UserModel)
│       ├── schemas.py           # Pydantic request/response validation schemas (DTOs)
│       ├── dependencies.py      # Dependency injection composition (replaces NestJS module)
│       └── exceptions.py        # Domain-specific exceptions
├── db/                          # Database connection and Unit of Work setup
│   ├── base.py                  # Shared DeclarativeBase for models
│   ├── session.py               # Async engine and session factory
│   ├── unit_of_work.py          # Transaction boundary boundary manager
│   └── registry.py              # Central model registry for Alembic target metadata
├── core/                        # System-wide technical plumbing (CORS, lifespan, etc.)
├── shared/                      # Pure utilities shared across modules (security, logger, pagination)
└── workers/                     # Async background workers (arq)
```

---

## 3. Strict Architecture & Layering Rules

Every feature slice must implement a strict unidirectional flow of dependencies:

```text
HTTP Request → Router → Service → Repository → UnitOfWork / Session → Database
```

### A. The Router Layer (Thin & HTTP-Only)

- **Role**: Parse incoming requests, trigger schema validation, call the appropriate service, and return responses.
- **Rules**:
  - Must stay thin. Do not place business logic in routers.
  - Must declare a `response_model` to serve as a firewall, preventing database secrets (e.g., `hashed_password`) from leaking.
  - Can raise `HTTPException` if there are HTTP-specific concerns (e.g., authorization failures).
  - Version prefixes (e.g. `/api/v1`) are applied once in `src/api/router.py`; do not prefix module routers.

### B. The Service Layer (Domain Orchestration)

- **Role**: Coordinates the use-case. Performs validation, invokes domain entities, and handles database transaction boundaries.
- **Rules**:
  - **Framework-Agnostic**: Never import `fastapi` or raise `HTTPException` in services.
  - **Domain Exceptions**: Raise domain-specific exceptions (e.g., `UserNotFound`). They will be translated into HTTP responses centrally in `core/exception_handlers.py`.
  - **Transaction Boundary**: The service must drive transaction boundaries. Call `await self.uow.commit()` only after all database operations are completed.

### C. The Repository Layer (Data Access Only)

- **Role**: Reads and writes persistence models to the database. Maps SQLAlchemy models (e.g., `UserModel`) to domain entities (e.g., `User`).
- **Rules**:
  - **No Commits**: Repositories must **never** call `session.commit()`. They use `session.flush()` to let the Unit of Work control transaction boundaries.
  - Use modern, pure SQLAlchemy 2.0 select syntax (`select(Model).where(...)`).
  - Distinguish between **Domain Entities** (used for writes/validation) and **Read Projections** (descriptive join models used for optimized reads/GET routes).

### D. The Domain Entity Layer (Business Invariants)

- **Role**: Pure Python objects representing domain rules and state validations (e.g., `deactivate()` methods).
- **Rules**:
  - Separate from persistence models. Do not define database columns or ORM behaviors inside entities.
  - Keep retrieve paths join-free.

---

## 4. Coding Conventions & Best Practices

### Manual Dependency Injection

- Do not use a runtime DI container. Instead, compose dependencies manually in `dependencies.py` using FastAPI's `Depends`.
- **Constructor Style**: Use **keyword arguments** to instantiate classes (`UserService(repository=repo, uow=uow)`).
- If a class has 3+ dependencies, group them inside a frozen `dataclass` (e.g. `UserServiceDeps`) to minimize parameter bloat.
- Do not inject loggers or metrics clients; initialize them as module-level singletons.

### Database Transactions & Unit of Work (UoW)

- Multi-repository writes must occur atomically within a single transaction managed by `UnitOfWork` (e.g., updating a user and adding an audit log).
- Since FastAPI caches dependencies per-request, `UserRepository` and `UnitOfWork` will share the same `AsyncSession` seamlessly.

### Cross-Module Isolation

- Modules must be treated as strictly encapsulated black boxes.
- If module A needs data from module B, **A's service must call B's service** via dependency injection.
- **Never** import another module's repository, models, or internal routers directly.
- The only cross-module imports allowed are from public exports in `__init__.py` (re-exporting service, entities, and public types, but **never** the router).

### Flat First, Promote Later

- Keep module files flat until code size grows past ~300-400 lines or starts losing cohesion.
- Only promote a single file (like `service.py`) to a package folder (`service/`) when necessary, and maintain public exports via `__init__.py` to avoid breaking downstream import paths.
  *(Exception: The auth module's `dependencies/` folder is a recognized exception, grouping the module's dependency wiring, authentication gates, and RBAC guards into a single sub-package for cohesion and import safety, while exposing gates/guards through the module root facade).*

---

## 5. Development Workflows

### How to Add a New Feature Module

1. Create a folder under `src/modules/<feature_name>/`.
2. Define the persistence model (`models.py`) and inherit from `src.db.base.Base`.
3. Add the model to the central metadata registry in `src/db/registry.py` so Alembic can find it.
4. Generate the database migration:

   ```bash
   alembic revision --autogenerate -m "feat: add <feature_name> table"
   ```

5. Implement schemas (`schemas.py`), domain entity (`entities.py`), repository (`repository.py`), exceptions (`exceptions.py`), and service (`service.py`).
6. Wire dependencies in `dependencies.py` and implement routes in `router.py`.
7. Register the new router in `src/api/router.py`.
8. Write tests in `tests/modules/<feature_name>/`.

### Code Style & Verification

- Run code formatters and linters (`ruff` and `pyright`) before submitting changes.
- Ensure all public functions have PEP 257 compliant docstrings (using imperative mood, e.g., `"Retrieve user profile by ID."`).
- Add appropriate type annotations to all arguments and return values.

---

Use this guide as your architectural North Star while working on this codebase. Sticking to these guidelines ensures clean, modular, and highly performant code.
