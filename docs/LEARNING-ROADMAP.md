# AsyncPulse — Learning Roadmap

> Step-by-step guide to building this app, from Python foundations to a production-ready API.

---

## Phase 1: Python Foundations (before touching FastAPI)

### 1.1 Python Syntax & Data Types

- [ ] Variables, strings, f-strings
- [ ] Lists, tuples, dicts, sets
- [ ] Conditionals, loops
- [ ] Functions (positional args, kwargs, defaults)
- [ ] List/dict comprehensions

**Practice:** Write a script that reads a CSV file and prints summary stats.

### 1.2 Type Hints & Pydantic Basics

- [ ] Type hints: `str`, `int`, `Optional[str]`, `list[dict]`
- [ ] Function signatures with return types
- [ ] Pydantic `BaseModel` — define a schema, validate data
- [ ] Field constraints: `min_length`, `max_length`, `ge`, `le`
- [ ] `model_dump()`, `model_validate()`, `from_attributes`

**Practice:** Define `UserCreate` and `UserUpdate` schemas, test validation
errors by passing bad data.

### 1.3 Async/Await Fundamentals

- [ ] What is async — cooperative multitasking vs threads
- [ ] `async def` and `await` syntax
- [ ] `asyncio.run()`, event loop basics
- [ ] `asyncio.gather()` — run concurrent tasks
- [ ] When to use async vs sync (I/O-bound vs CPU-bound)

**Practice:** Write an async script that fetches 5 URLs concurrently with `aiohttp`
or `httpx.AsyncClient`, compare timing to sequential requests.

### 1.4 Error Handling

- [ ] `try / except / else / finally`
- [ ] Catching specific exceptions
- [ ] Raising custom exceptions
- [ ] `HTTPException` in FastAPI context

**Practice:** Write a function that fetches a URL and retries on failure (3 attempts).

---

## Phase 2: FastAPI Core

### 2.1 First FastAPI App

- [ ] Install FastAPI + uvicorn
- [ ] `app = FastAPI()`, `@app.get("/")`, `uvicorn src.main:app --reload`
- [ ] Path parameters: `@app.get("/users/{user_id}")`
- [ ] Query parameters: `@app.get("/users?page=1&size=20")`
- [ ] Request body with Pydantic model
- [ ] Response models (`response_model=...`)

**Practice:** Build a minimal `/items` CRUD (in-memory list, no DB yet).

### 2.2 Dependency Injection

- [ ] What is DI — injecting services via function parameters
- [ ] `Depends()` — the core mechanism
- [ ] Dependency chains: A depends on B, B depends on C
- [ ] `yield` dependencies (for DB sessions, cleanup)
- [ ] Dependency overrides (for testing)

**Practice:** Create `get_db()` dependency that yields a mock session. Use it in a route.

### 2.3 APIRouter & Project Structure

- [ ] `APIRouter(prefix="/users", tags=["users"])` (version prefix added by aggregator)
- [ ] `app.include_router(router)` — modular routing
- [ ] File structure: `router.py`, `service.py`, `repository.py`
- [ ] Separation of concerns: routes → service → repository

**Practice:** Refactor your `/items` CRUD into router/service/repository files.

### 2.4 Request Validation & Error Responses

- [ ] `Query()`, `Path()`, `Body()` — parameter metadata
- [ ] 422 validation error responses (automatic)
- [ ] Custom error responses with `responses={}`
- [ ] `HTTPException(status_code=404, detail="Not found")`

**Practice:** Add input validation to your routes, return proper error codes.

---

## Phase 3: Database Layer

### 3.1 SQLAlchemy 2.0 ORM Basics

- [ ] `DeclarativeBase` + `Mapped` / `mapped_column` typed models
- [ ] Persistence model vs domain entity — why they're separate
- [ ] `mapped_column(primary_key=True, unique=True, index=True)`
- [ ] Relationships (one-to-many, many-to-many) — defer to Phase 6
- [ ] `select()`, `.where()`, `.offset()`, `.limit()`
- [ ] `session.execute()` + `.scalar_one_or_none()` / `.scalars().all()`

**Practice:** Define `UserModel`, create a script that inserts and queries a user.

### 3.2 Async SQLAlchemy Sessions

- [ ] `create_async_engine("postgresql+asyncpg://...")`
- [ ] `async_sessionmaker` + `AsyncSession`
- [ ] `get_async_session()` as a FastAPI dependency (yield)
- [ ] `await session.execute(select(UserModel).where(...))`
- [ ] `session.add()`, `session.flush()`, `session.refresh()`

**Practice:** Wire up a real PostgreSQL DB (Docker), query users from a FastAPI route.

### 3.3 Repository + Domain Entity + Unit of Work

- [ ] Why repository — abstract DB access from business logic
- [ ] `UserRepository` class with `__init__(self, session: AsyncSession)`
- [ ] Map persistence model ↔ domain entity (`_to_entity`)
- [ ] Domain entity holds behavior (`deactivate()`, `verify_password()`)
- [ ] Unit of Work owns commit/rollback — repositories never commit
- [ ] Pagination: `offset/limit` + total count

**Practice:** Implement `UserRepository` (returns entities) + a `UnitOfWork`, and
have the service commit through the UoW.

### 3.4 Alembic Migrations

- [ ] `alembic init`, configure `env.py` for async
- [ ] Generate migration: `alembic revision --autogenerate -m "create users table"`
- [ ] Apply: `alembic upgrade head`
- [ ] Rollback: `alembic downgrade -1`
- [ ] Migration conventions (add column, rename, etc.)

**Practice:** Create initial migration, add a new column, generate second migration.

---

## Phase 4: Auth & Security

### 4.1 Password Hashing

- [ ] Why hash — never store plain text
- [ ] `passlib[bcrypt]` — `hash_password()`, `verify_password()`
- [ ] Salt — why it exists, how bcrypt handles it
- [ ] Never log or return hashed passwords

**Practice:** Write `hash_password()` and `verify_password()` utility functions.

### 4.2 JWT Tokens

- [ ] JWT structure: header, payload, signature
- [ ] `python-jose` — `jwt.encode()`, `jwt.decode()`
- [ ] Access token (short-lived, 30 min)
- [ ] Refresh token (long-lived, 7 days)
- [ ] Token payload: `sub` (user ID), `exp` (expiry), `type` (access/refresh)

**Practice:** Write `create_access_token()` and `create_refresh_token()` functions.

### 4.3 Auth Routes & Flow

- [ ] `POST /auth/register` — create user + return tokens
- [ ] `POST /auth/login` — verify credentials + return tokens
- [ ] `POST /auth/refresh` — swap refresh token for new access token
- [ ] `OAuth2PasswordBearer(tokenUrl="/auth/login")` — Swagger auth
- [ ] `get_current_user()` dependency — extract user from token

**Practice:** Implement full register → login → get profile flow. Test in Swagger.

### 4.4 Route Protection & Permissions

- [ ] `Depends(get_current_user)` on protected routes
- [ ] `Depends(get_current_active_user)` — check `is_active`
- [ ] Role-based: `is_superuser` check
- [ ] Owner-only: user can only update their own profile
- [ ] 401 vs 403 — unauthorized vs forbidden

**Practice:** Protect `/users/me`, allow only superuser to list all users.

---

## Phase 5: Testing

### 5.1 Test Setup

- [ ] `pytest` + `pytest-asyncio`
- [ ] `httpx.AsyncClient` with `ASGITransport` — async TestClient
- [ ] `conftest.py` — fixtures for DB session, client, test data
- [ ] `app.dependency_overrides[get_db] = test_db` — mock dependencies

**Practice:** Set up test DB (Docker PostgreSQL), create basic test fixtures.

### 5.2 Unit Tests

- [ ] Test service layer in isolation (mock repository)
- [ ] Test validation (Pydantic schemas reject bad input)
- [ ] Test password hashing (hash matches, wrong password fails)
- [ ] Test JWT creation/decoding (valid token, expired token)

**Practice:** Write unit tests for `UserService.create_user()`.

### 5.3 Integration Tests

- [ ] Test full request/response cycle through routes
- [ ] Test DB operations against test database
- [ ] Test auth flow: register → login → access protected route
- [ ] Test error cases: duplicate email, wrong password, expired token

**Practice:** Write integration tests for all `/users` endpoints.

### 5.4 Test Patterns

- [ ] Arrange-Act-Assert structure
- [ ] Fixtures vs factory functions
- [ ] Parametrized tests (`@pytest.mark.parametrize`)
- [ ] Test coverage: `pytest --cov=src`

**Practice:** Achieve 80%+ coverage on the users module.

---

## Phase 6: Advanced Topics (after basics work)

### 6.1 SQLAlchemy Relationships

- [ ] One-to-many: `User` has many `Post`
- [ ] Many-to-many: `User` ↔ `Role`
- [ ] `sa_relationship()` with `back_populates`
- [ ] Eager vs lazy loading (async context)

### 6.2 Background Tasks

- [ ] FastAPI `BackgroundTasks` — simple async tasks
- [ ] ARQ or Celery — task queues for heavy work
- [ ] Use case: send welcome email after registration

### 6.3 Rate Limiting

- [ ] `slowapi` middleware — per-route or global limits
- [ ] Rate limit by IP or by authenticated user
- [ ] Return 429 with `Retry-After` header

### 6.4 WebSocket Support

- [ ] `@app.websocket("/ws")` — real-time connections
- [ ] Broadcast to connected clients
- [ ] Use case: live notifications

### 6.5 API Key Auth

- [ ] `X-API-Key` header authentication
- [ ] `APIKeyHeader` dependency
- [ ] Use case: third-party integrations

---

## Phase 7: Production Ready

### 7.1 Configuration Management

- [ ] `pydantic-settings` — `BaseSettings` with `.env` file
- [ ] Separate configs: `dev`, `staging`, `production`
- [ ] Secret management (env vars, not hardcoded)

### 7.2 Docker & Deployment

- [ ] `Dockerfile` — multi-stage build
- [ ] `docker-compose.yml` — API + PostgreSQL + Redis
- [ ] Health check endpoint: `GET /health`
- [ ] Gunicorn + Uvicorn workers for production

### 7.3 Logging & Monitoring

- [ ] `structlog` or Python `logging` module
- [ ] Request ID middleware (trace requests)
- [ ] Prometheus metrics endpoint

### 7.4 Documentation

- [ ] OpenAPI docs at `/docs` (Swagger UI)
- [ ] ReDoc at `/redoc`
- [ ] API description, tags, examples in router decorators
- [ ] Changelog and contributing guide in repo

---

## Quick Reference: Commands

```bash
# Dev setup
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn sqlalchemy asyncpg python-jose passlib bcrypt httpx
pip install structlog prometheus-client opentelemetry-sdk arq redis
pip install -e ".[dev]"  # pytest, ruff, pyright

# Run server
uvicorn src.main:app --reload

# Database
docker run -d --name pg -p 5432:5432 -e POSTGRES_DB=asyncpulse -e POSTGRES_PASSWORD=postgres postgres:16-alpine
alembic revision --autogenerate -m "description"
alembic upgrade head

# Test
pytest -v
pytest --cov=src --cov-report=term-missing

# Lint
ruff check src/
pyright src/
```
