# async-pulse

Python async REST API built with FastAPI + SQLAlchemy 2.0 for user management.

Learning project covering async/await, Pydantic validation, dependency injection,
and PostgreSQL via SQLAlchemy — the Python bridge from NestJS/TypeScript.

## Tech Stack

- **FastAPI** — async Python web framework (feels like NestJS)
- **SQLAlchemy 2.0 ORM** — pure SQLAlchemy (not SQLModel) for real ORM fundamentals
- **PostgreSQL 16** — async via asyncpg
- **Alembic** — database migrations
- **Pydantic v2** — request/response validation (replaces Zod)
- **JWT Auth** — access + refresh tokens
- **pytest** — async tests with httpx
- **Observability** — structlog + prometheus-client + OpenTelemetry
- **Workers** — arq (async background jobs)

> **Why pure SQLAlchemy, not SQLModel?** SQLModel hides important ORM concepts.
> Using SQLAlchemy directly builds stronger fundamentals: session lifecycle,
> transactions, Unit of Work, relationship loading, and ORM-vs-domain separation.

## Architecture

Feature-first modular monolith with layered internals:

```
Router → Application Service → Domain Entity → Repository → Unit of Work → SQLAlchemy → PostgreSQL
```

It borrows selectively from DDD — a thin **domain-entity** layer (business
behavior, kept separate from persistence models) plus an explicit **Unit of
Work** for transaction boundaries — while stopping short of full DDD (no
aggregates/value objects/domain events) to stay onboarding-friendly ("DDD-lite").

Layering rules: routers are thin; services are framework-agnostic and raise
**domain exceptions** (never `HTTPException`); domain entities hold business
invariants separate from persistence models; repositories do data access only and
never commit (the **Unit of Work** owns transactions); domain errors are
translated to HTTP once in `core/exception_handlers.py`. Always set
`response_model` so persistence fields like `hashed_password` never leak.

## Project Structure

```
src/
├── main.py                      # App wiring: middleware, handlers, routers, /health
├── modules/
│   ├── auth/                    # auth feature slice
│   └── users/
│       ├── router.py            # HTTP routes (thin)
│       ├── service.py           # Use-case logic (no fastapi imports)
│       ├── repository.py        # Data access; maps model ↔ entity
│       ├── entities.py          # Domain entity + business behavior
│       ├── models.py            # SQLAlchemy persistence model
│       ├── schemas.py           # Pydantic request/response DTOs
│       ├── dependencies.py      # FastAPI Depends() wiring
│       └── exceptions.py        # Domain exceptions
├── db/                          # SQLAlchemy plumbing only
│   ├── base.py                  # DeclarativeBase
│   ├── session.py               # Async engine + session factory
│   ├── unit_of_work.py          # Transaction boundary
│   └── registry.py              # All models → target_metadata for Alembic
├── core/                        # App-level technical wiring only
│   ├── settings.py              # pydantic-settings (single config source)
│   ├── lifespan.py              # Startup/shutdown
│   ├── middleware.py            # CORS, request-id, access log
│   └── exception_handlers.py   # domain exception → HTTP (registered once)
├── shared/                      # Reusable utilities, no framework/DB imports
│   ├── security.py              # hash_password, verify_password, JWT
│   ├── pagination.py            # PageParams, PagedResponse
│   ├── exceptions.py            # AppError base + shared hierarchy
│   ├── constants.py             # Shared enums / string literals
│   └── logger.py                # structlog setup + get_logger()
└── workers/                     # Background jobs only (arq)
    ├── tasks.py
    └── scheduler.py
```

## NestJS → FastAPI Translation

| NestJS | FastAPI |
|---|---|
| `@Controller('users')` | `router = APIRouter(prefix="/users")` |
| `@Injectable() class UserService` | `class UserService` (no decorator) |
| Constructor DI | `Depends()` on function params |
| Zod schemas | Pydantic BaseModel |
| TypeORM/Drizzle queries | SQLAlchemy 2.0 `select()` |
| Entity classes | `entities.py` domain entities |

## Setup

```bash
# Clone
git clone https://github.com/KartikRanjan/async-pulse.git
cd async-pulse

# Start dev environment
docker compose up -d

# Or locally
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run
fastapi dev src/main.py

# Docs
open http://localhost:8000/docs
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | Liveness probe |
| GET | /api/v1/users/ | List users (paginated) |
| GET | /api/v1/users/me | Current user profile |
| GET | /api/v1/users/{id} | Get user by ID |
| POST | /api/v1/users/ | Create user |
| PATCH | /api/v1/users/{id} | Update user |
| DELETE | /api/v1/users/{id} | Soft-delete user |

> The `/api/v1` prefix is applied once by the aggregator in `src/api/router.py`;
> module routers use a bare `/users` prefix.

## Development Roadmap

- [ ] Project scaffold + Docker Compose
- [ ] Reconcile scaffold to `modules/` layout; align pyproject (py3.11+, ruff)
- [ ] db/ setup: Base, async session, Unit of Work
- [ ] User persistence model + domain entity + migration
- [ ] Domain exceptions + central handlers
- [ ] CRUD routes
- [ ] Tests
- [ ] JWT auth flow
- [ ] Role-based access control
- [ ] Observability (structlog, Prometheus, OpenTelemetry)
- [ ] Background workers (arq) + Redis caching

## License

MIT
