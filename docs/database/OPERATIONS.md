# Database Definition & Operations Guide

This document details how to define database models, implement repository classes, orchestrate transactions in services, and wire dependencies in the AsyncPulse codebase.

---

## 1. Defining a Database Model (SQLAlchemy 2.0 ORM)

All persistence models in AsyncPulse map to database tables and are defined using modern SQLAlchemy 2.0 declarative mapping. They must reside in their respective module's `models.py` file.

### Rules for Model Definition

1. **Inheritance**: Models must subclass the centralized declarative `Base` from [base.py](../../src/db/base.py). This base automatically configures the PostgreSQL schema (e.g., `settings.DB_SCHEMA`).
2. **Tablename**: Declare `__tablename__` explicitly.
3. **Type Annotations**: Use `Mapped[T]` for all table columns to enforce type safety.
4. **Column Configuration**: Define column properties, defaults, constraints, and relationships using `mapped_column()`.
5. **Decoupling**: Models are persistence representations only. Domain rules and business invariants live inside domain entities in `entities.py`.

### Example Model Definition

Here is a simplified example based on [UserModel](../../src/modules/users/models.py):

```python
import uuid
from datetime import UTC, datetime
from sqlalchemy import DateTime, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from src.db.base import Base
from src.modules.users.entities import UserRole, UserStatus

def _utcnow() -> datetime:
    return datetime.now(UTC)

class UserModel(Base):
    """User persistence model — maps to the 'users' table."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))

    # Enum mapping (persisted as strings)
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus, native_enum=False, length=50),
        default=UserStatus.ACTIVE,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )
```

### Registry Registration

SQLAlchemy only registers models on `Base.metadata` when their files are imported. For Alembic to detect model changes for migrations:
- Import your new model in [registry.py](../../src/db/registry.py).
- Export it in `__all__` in `registry.py`.

---

## 2. Managing Migrations (Alembic)

We do **not** use `Base.metadata.create_all()` in the application runtime. Instead, Alembic owns all schema migrations.

### Commands to Run

```bash
# Generate a new migration after model changes
make migrate-gen m="feat: add new table"

# Apply all pending migrations (uses DIRECT_DATABASE_URL to bypass pgbouncer transaction pooling)
make migrate-up

# Rollback one migration step
make migrate-down
```

---

## 3. Implementing the Repository Layer

The repository layer handles database queries and maps SQLAlchemy persistence models to pure domain entities. It sits in the module's `repository.py` file.

### Rules for Repositories

1. **No Commits**: Repositories must **never** call `self.session.commit()`. Instead, they use `self.session.flush()` (or rely on SQLAlchemy's auto-flush) so the transaction boundary is driven by the Service via the `UnitOfWork`.
2. **Modern SQL Syntax**: Use SQLAlchemy 2.0 selection patterns (`select()`, `where()`, `or_()`, `func.count()`).
3. **Entity Mapping**: Map SQLAlchemy models (e.g., `UserModel`) to domain entities (e.g., `User`) using a mapping helper before returning them to services.
4. **Encapsulation**: Distinguish between writes/updates and read projections. Profile updates should be separate from credential updates (see privileged writes in [UserRepository](../../src/modules/users/repository.py)).

### Example Repository Implementation

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.users.entities import User
from src.modules.users.models import UserModel

class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        """Map a persistence model to a domain entity."""
        return User(
            user_id=model.id,
            email=model.email,
            username=model.username,
            hashed_password=model.hashed_password,
            status=model.status,
        )

    async def get_by_id(self, user_id: str) -> User | None:
        """Fetch an entity by primary key."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, user: User) -> User:
        """Persist a new entity model. Flushes but does NOT commit."""
        model = UserModel(
            id=user.id,
            email=user.email,
            username=user.username,
            hashed_password=user.hashed_password,
        )
        self.session.add(model)
        await self.session.flush()  # Populates autogenerated fields (e.g., id, timestamps)
        return self._to_entity(model)

    async def update(self, user: User) -> User:
        """Merge updates and flush."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user.id)
        )
        model = result.scalar_one()
        model.email = user.email
        model.username = user.username
        await self.session.flush()
        return self._to_entity(model)
```

---

## 4. Orchestrating Database Operations in Services

Services coordinate the use-cases and manage database transaction boundaries. They live in `service.py`.

### Rules for Services

1. **Framework-Agnostic**: Never import FastAPI, requests, or raise `HTTPException` inside services. Use domain-specific exceptions instead.
2. **Transaction Boundaries**: Utilize `UnitOfWork` (`uow`) to explicitly control commit and rollback operations.
3. **No Direct Repository Commits**: The service determines when all operations in a transaction have succeeded and calls `await self.uow.commit()`.

### Example Service Implementation

Here is a simplified example based on [UserService](../../src/modules/users/service.py):

```python
from src.db.unit_of_work import UnitOfWork
from src.modules.users.entities import User
from src.modules.users.repository import UserRepository
from src.modules.users.exceptions import UserAlreadyExistsError

class UserService:
    def __init__(self, repository: UserRepository, uow: UnitOfWork) -> None:
        self.repo = repository
        self.uow = uow

    async def register_user(self, email: str, username: str, password_hash: str) -> User:
        """Orchestrate registration use-case. Rollbacks are automatic if an exception occurs."""
        # 1. Validation
        existing = await self.repo.get_by_email(email)
        if existing:
            raise UserAlreadyExistsError("A user with this email already exists")

        # 2. Mutative operation (flush only)
        user = await self.repo.create(
            User(email=email, username=username, hashed_password=password_hash)
        )

        # 3. Explicit Commit at transaction boundary
        await self.uow.commit()
        return user
```

---

## 5. Dependency Injection & Dependency Wiring

Dependencies are composed manually in `dependencies.py` using FastAPI's dependency injection mechanisms.

### Composition Guidelines

- **FastAPI Depends**: Resolve `AsyncSession` and `UnitOfWork` using dependencies from `src.db.session` and `src.db.unit_of_work`.
- **Constructor Style**: Always instantiate classes using **keyword arguments** to prevent positional argument issues.
- **Cross-Module Isolation**: Do not import other modules' repositories or models directly. Communicate with other modules using their public services injected at the dependency layer.

### Example Wiring in `dependencies.py`

Here is a representative pattern based on [users/dependencies.py](../../src/modules/users/dependencies.py):

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.session import get_async_session
from src.db.unit_of_work import UnitOfWork, get_unit_of_work
from src.modules.users.repository import UserRepository
from src.modules.users.service import UserService

async def get_user_service(
    session: AsyncSession = Depends(get_async_session),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> UserService:
    """FastAPI dependency — builds and returns a UserService instance."""
    repository = UserRepository(session)
    return UserService(
        repository=repository,
        uow=uow,
    )
```
