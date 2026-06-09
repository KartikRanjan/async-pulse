# FastAPI Users — Design Document

> A Python async REST API for user management, built as a learning bridge from
> NestJS/TypeScript to modern Python backend development.

---

## 1. Why This Project

| Concept | NestJS / TypeScript | Python / FastAPI |
|---|---|---|
| Routing | Decorators + `@Controller` | Decorators + `@app.get()` |
| Validation | Zod / class-validator | Pydantic (same concept, native) |
| DI | NestJS IoC container | FastAPI `Depends()` |
| ORM | Drizzle / TypeORM | SQLModel (SQLAlchemy + Pydantic) |
| Async | Node event loop | Python `async/await` (uvicorn + asyncio) |
| DB Driver | pg (node-postgres) | asyncpg (native async PostgreSQL) |

FastAPI feels familiar coming from NestJS — decorators, DI, typed schemas — but
the async model is explicit `async/await` rather than Node's implicit event loop.

---

## 2. Tech Stack

```
Runtime:      Python 3.11+
Server:       FastAPI + Uvicorn (ASGI)
Validation:   Pydantic v2 (built into FastAPI)
ORM:          SQLModel (SQLAlchemy 2.0 core + Pydantic models)
Database:     PostgreSQL 16 (async via asyncpg)
Migrations:   Alembic
Auth:         JWT (access + refresh tokens) via python-jose + passlib[bcrypt]
Testing:      pytest + pytest-asyncio + httpx (async TestClient)
Linting:      ruff + mypy
```

---

## 3. Folder Structure

```
fastapi-users/
├── docs/
│   └── DESIGN.md               # this file
├── src/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan, middleware
│   ├── config.py                # Settings via pydantic-settings (env loading)
│   ├── database.py              # Async engine, session factory, Base model
│   │
│   ├── modules/
│   │   └── users/
│   │       ├── __init__.py
│   │       ├── router.py        # API routes (GET, POST, PATCH, DELETE)
│   │       ├── service.py       # Business logic (async functions)
│   │       ├── repository.py    # DB queries (SQLModel/SQLAlchemy async)
│   │       ├── schemas.py       # Pydantic request/response DTOs
│   │       ├── models.py        # SQLModel table definitions
│   │       ├── dependencies.py  # DI: get_current_user, get_db_session
│   │       └── exceptions.py    # User-specific errors
│   │
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── pagination.py        # Reusable pagination params + response
│   │   ├── errors.py            # Global exception handlers
│   │   └── auth.py              # JWT utils, password hashing
│   │
│   └── core/
│       ├── __init__.py
│       └── events.py            # Startup/shutdown event handlers
│
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/                # migration files
│
├── tests/
│   ├── conftest.py              # Fixtures: async client, test DB session
│   ├── test_users_router.py     # Route-level tests (httpx AsyncClient)
│   ├── test_users_service.py    # Unit tests for business logic
│   └── test_users_repository.py # Integration tests against test DB
│
├── pyproject.toml               # Project metadata, dependencies, ruff/mypy config
├── Dockerfile
├── docker-compose.yml           # PostgreSQL + API dev environment
├── .env.example
└── README.md
```

### Why this structure matters

```
modules/users/ mirrors the NestJS pattern you already know:
  router.py    ≈  users.controller.ts
  service.py   ≈  users.service.ts
  repository.ts ≈  (Drizzle queries, but here it's SQLModel)
  schemas.py   ≈  DTOs + Zod schemas (Pydantic does both)
  models.py    ≈  Drizzle schema definition
```

The difference: Python doesn't use classes for services. Everything is
**functions + dependency injection via `Depends()`**. No decorators like
`@Injectable()` — FastAPI resolves dependencies at request time by inspecting
type hints.

---

## 4. User Module — Detailed Design

### 4.1 Database Model (SQLModel)

```python
# src/modules/users/models.py

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    """User table — doubles as a Pydantic model for reads."""
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    username: str = Field(unique=True, index=True, max_length=50)
    hashed_password: str = Field(max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

SQLModel = SQLAlchemy table + Pydantic model in one class. No duplication.

### 4.2 Pydantic Schemas (Request/Response DTOs)

```python
# src/modules/users/schemas.py

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# --- Request schemas ---

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    full_name: Optional[str] = None
    is_active: Optional[bool] = None


# --- Response schemas ---

class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: Optional[str]
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

```python
# src/modules/users/dependencies.py

from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import AsyncSession

from src.config import settings
from src.database import get_async_session
from src.modules.users.models import User
from src.modules.users.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_user_repository(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[UserRepository, None]:
    """Provide a UserRepository per request — same as NestJS @Inject()."""
    yield UserRepository(session)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Extract and validate the current user from JWT."""
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
```

**How `Depends()` works:**
- FastAPI inspects the function signature
- Sees `repo: UserRepository = Depends(get_user_repository)`
- Calls `get_user_repository(session=...)` — which itself depends on `get_async_session`
- Chains the full dependency tree automatically
- Caches per-request (same instance if reused in multiple places)

This is conceptually identical to NestJS's DI container, but simpler — no
decorators, no modules, no providers array. Just function signatures.

### 4.4 Repository (DB Queries)

```python
# src/modules/users/repository.py

from typing import Optional
from uuid import UUID

from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.users.models import User
from src.modules.users.schemas import UserCreate, UserUpdate


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.exec(
            select(User).where(User.email == email)
        )
        return result.first()

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.exec(
            select(User).where(User.username == username)
        )
        return result.first()

    async def create(self, data: UserCreate, hashed_password: str) -> User:
        user = User(**data.model_dump(), hashed_password=hashed_password)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user: User, data: UserUpdate) -> User:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_users(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[User], int]:
        # Total count
        count_result = await self.session.exec(select(func.count(User.id)))
        total = count_result.one()

        # Paginated results
        offset = (page - 1) * page_size
        result = await self.session.exec(
            select(User).offset(offset).limit(page_size)
        )
        return list(result.all()), total
```

**Compared to Drizzle:** Same idea — thin data-access layer. SQLModel uses
`select()` like Drizzle's `db.select()`, but everything is `await`-able
because the session is async.

### 4.5 Service Layer (Business Logic)

```python
# src/modules/users/service.py

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status

from src.modules.users.models import User
from src.modules.users.repository import UserRepository
from src.modules.users.schemas import UserCreate, UserUpdate
from src.shared.auth import hash_password


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def get_user(self, user_id: UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def create_user(self, data: UserCreate) -> User:
        # Check uniqueness
        if await self.repository.get_by_email(data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        if await self.repository.get_by_username(data.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )

        hashed = hash_password(data.password)
        return await self.repository.create(data, hashed)

    async def update_user(self, user_id: UUID, data: UserUpdate) -> User:
        user = await self.get_user(user_id)
        return await self.repository.update(user, data)

    async def list_users(
        self, page: int = 1, page_size: int = 20
    ) -> dict:
        users, total = await self.repository.list_users(page, page_size)
        return {
            "items": users,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
```

### 4.6 Router (API Routes)

```python
# src/modules/users/router.py

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.modules.users.dependencies import (
    get_current_user,
    get_user_repository,
)
from src.modules.users.models import User
from src.modules.users.repository import UserRepository
from src.modules.users.schemas import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from src.modules.users.service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def get_user_service(
    repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    """Inject UserService with its repository dependency."""
    return UserService(repo)


@router.get("/", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: UserService = Depends(get_user_service),
):
    return await service.list_users(page, page_size)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    service: UserService = Depends(get_user_service),
):
    return await service.get_user(user_id)


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    data: UserCreate,
    service: UserService = Depends(get_user_service),
):
    return await service.create_user(data)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    # Only allow self-update (or superuser — add check here)
    if str(current_user.id) != str(user_id) and not current_user.is_superuser:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized")
    return await service.update_user(user_id, data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    if not current_user.is_superuser:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized")
    await service.update_user(user_id, UserUpdate(is_active=False))
```

---

## 5. App Factory & Lifespan

```python
# src/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import create_db_and_tables
from src.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables (dev) / run migrations (prod). Shutdown: cleanup."""
    if settings.ENV == "development":
        await create_db_and_tables()
    yield
    # Shutdown: close pool, etc.


app = FastAPI(
    title="FastAPI Users",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
```

---

## 6. Database Setup (Async SQLAlchemy)

```python
# src/database.py

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,  # postgresql+asyncpg://...
    echo=settings.ENV == "development",
    pool_size=20,
    max_overflow=10,
)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session
```

---

## 7. Config (Pydantic Settings)

```python
# src/config.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fastapi_users"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

---

## 8. Test Fixtures

```python
# tests/conftest.py

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from src.database import get_async_session
from src.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/fastapi_users_test"


@pytest_asyncio.fixture
async def test_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


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
    #   user = await repository.get_by_id(user_id) # async
    #     result = await session.exec(select(...))  # async
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
      POSTGRES_DB: fastapi_users
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
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/fastapi_users
    depends_on:
      - db

volumes:
  pgdata:
```

---

## 11. Development Roadmap

```
Phase 1: Foundation (current)
  [x] Design doc (this file)
  [ ] Project scaffold (pyproject.toml, Dockerfile, docker-compose)
  [ ] Config + database setup
  [ ] User model + migration
  [ ] CRUD routes (list, get, create, update, soft-delete)
  [ ] Tests for all routes

Phase 2: Auth
  [ ] JWT access + refresh token flow
  [ ] Login / logout endpoints
  [ ] Password reset flow
  [ ] Role-based access control

Phase 3: Expand
  [ ] Second module (posts, notifications, whatever)
  [ ] Background tasks (Celery or ARQ)
  [ ] WebSocket support
  [ ] Rate limiting
  [ ] API key auth
```
