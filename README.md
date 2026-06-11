# async-pulse

Python async REST API built with FastAPI + SQLModel for user management.

Learning project covering async/await, Pydantic validation, dependency injection,
and PostgreSQL via SQLAlchemy — the Python bridge from NestJS/TypeScript.

## Tech Stack

- **FastAPI** — async Python web framework (feels like NestJS)
- **SQLModel** — SQLAlchemy + Pydantic in one class (replaces Drizzle)
- **PostgreSQL 16** — async via asyncpg
- **Alembic** — database migrations
- **Pydantic v2** — request/response validation (replaces Zod)
- **JWT Auth** — python-jose + passlib[bcrypt]
- **pytest** — async tests with httpx

## Project Structure

```
src/
├── main.py                  # App factory, lifespan, middleware
├── config.py                # Settings via pydantic-settings
├── database.py              # Async engine + session factory
├── modules/
│   └── users/
│       ├── router.py        # API routes
│       ├── service.py       # Business logic
│       ├── repository.py    # DB queries
│       ├── schemas.py       # Pydantic DTOs
│       ├── models.py        # SQLModel table definitions
│       ├── dependencies.py  # DI: get_current_user, get_db_session
│       └── exceptions.py    # User-specific errors
├── shared/
│   ├── pagination.py
│   ├── errors.py
│   └── auth.py              # JWT utils, password hashing
└── core/
    └── events.py
```

## NestJS → FastAPI Translation

| NestJS | FastAPI |
|---|---|
| `@Controller('users')` | `router = APIRouter(prefix="/users")` |
| `@Injectable() class UserService` | `class UserService` (no decorator) |
| Constructor DI | `Depends()` on function params |
| Zod schemas | Pydantic BaseModel |
| Drizzle queries | SQLModel select() |

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
| GET | /api/v1/users/ | List users (paginated) |
| GET | /api/v1/users/me | Current user profile |
| GET | /api/v1/users/{id} | Get user by ID |
| POST | /api/v1/users/ | Create user |
| PATCH | /api/v1/users/{id} | Update user |
| DELETE | /api/v1/users/{id} | Soft-delete user |

## Development Roadmap

- [ ] Project scaffold + Docker Compose
- [ ] Config + database setup
- [ ] User model + migration
- [ ] CRUD routes
- [ ] Tests
- [ ] JWT auth flow
- [ ] Role-based access control

## License

MIT
