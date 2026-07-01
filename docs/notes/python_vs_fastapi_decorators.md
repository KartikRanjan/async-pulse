# Python Decorators & Annotations vs. FastAPI Framework Metadata

This guide is designed for developers transitioning from **Java (Spring Boot)** or **TypeScript (NestJS)** to modern Python and FastAPI. It clarifies the differences between native Python decorators, type annotations, and FastAPI-specific decorators and dependency configurations, covering nearly all of your daily backend development needs.

---

## 1. Terminology Mapping: Decorators vs. Annotations

| Term | Java (Spring Boot) / TypeScript (NestJS) | Python / FastAPI |
| :--- | :--- | :--- |
| **Decorator / Annotation** | **Annotations (`@`)**: Metadata attached to classes, methods, or properties. They do not execute code directly; a reflection engine (JVM reflection or `reflect-metadata`) scans them at runtime or startup. | **Decorators (`@`)**: Syntactic sugar for a wrapper function. Writing `@my_decorator` on top of `func` translates to `func = my_decorator(func)`. They execute dynamic logic immediately when the module is imported. |
| **Type Metadata** | Declared in class properties or method signatures for compilation checks (TS) or runtime reflection (Java). | **Type Hints / Annotations**: Native syntax for defining types (e.g., `x: int`). Since Python is dynamically typed, these are ignored at execution time unless inspected by library code (Pydantic). |

---

## 2. Native Python Decorators & Annotations

### Key Built-In Decorators

#### A. `@property`

* **Purpose**: Exposes a method as a class attribute/getter. You can also define matching `.setter` and `.deleter` properties.
* **Java/TypeScript Equivalent**: standard getter/setter methods or Lombok's `@Getter`/`@Setter` annotations.

```python
class User:
    def __init__(self, first_name: str, last_name: str) -> None:
        self.first_name = first_name
        self.last_name = last_name

    @property
    def full_name(self) -> str:
        """Exposed as user.full_name instead of user.full_name()"""
        return f"{self.first_name} {self.last_name}"
```

#### B. `@staticmethod`

* **Purpose**: Defines a method that does not receive the instance context (`self`) or the class context (`cls`). It behaves like a plain function scoped under the class namespace.
* **Java/TypeScript Equivalent**: The `static` keyword on a method.

```python
class PasswordUtils:
    @staticmethod
    def is_strong(password: str) -> bool:
        return len(password) >= 12
```

#### C. `@classmethod`

* **Purpose**: Defines a method that receives the class object (`cls`) as its first argument instead of an instance (`self`). Commonly used to implement custom factory constructors.
* **Java/TypeScript Equivalent**: Static factory methods (e.g., `public static User of(...)`).

```python
class User:
    def __init__(self, username: str) -> None:
        self.username = username

    @classmethod
    def from_email(cls, email: str) -> "User":
        username = email.split("@")[0]
        return cls(username=username)  # Instantiates via cls
```

#### D. `@functools.lru_cache` and `@functools.cache`

* **Purpose**: Memoizes/caches the results of function calls based on arguments to save computing time on subsequent calls.
* **Java/TypeScript Equivalent**: `@Cacheable` in Spring Boot or custom caching interceptors.

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_expensive_config(key: str) -> str:
    # Simulating DB query or heavy parsing
    return f"value_for_{key}"
```

### Native Type Annotations

#### `typing.Annotated`

* **Purpose**: Introduced in Python 3.9, `Annotated[T, Metadata]` allows attaching arbitrary metadata to type declarations without affecting type checking.
* **Java/TypeScript Equivalent**: `@Autowired` or parameter annotations like `@RequestParam`.

```python
from typing import Annotated

# Declares a dependency type signature
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
```

---

## 3. Pydantic-Specific Validation Decorators

Pydantic utilizes decorators on model classes to perform complex object-level validations.

### A. `@field_validator`

* **Purpose**: Custom validator for a specific field.
* **Java/TypeScript Equivalent**: Custom JSR-380 `@Constraint` validator or class-validator custom constraints.

```python
from pydantic import BaseModel, field_validator

class UserCreate(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def username_must_not_contain_space(cls, v: str) -> str:
        if " " in v:
            raise ValueError("Username must not contain spaces")
        return v
```

### B. `@model_validator`

* **Purpose**: Custom validator that runs before (mode='before') or after (mode='after') the model is built, useful for multi-field cross-validation.
* **Java/TypeScript Equivalent**: Class-level constraint validation.

```python
from pydantic import BaseModel, model_validator

class RegisterRequest(BaseModel):
    password: str
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
```

---

## 4. FastAPI-Specific Decorators & Annotations

FastAPI combines Python's native decorators (for route registration) with Pydantic type annotations (for request/response parsing and validation).

### Routing Decorators (`@router.get`, `@router.post`, etc.)

* **Purpose**: Registers the decorated function as a route handler on the router. It is executed during startup to build the OpenAPI schema and route table.
* **Spring Boot / NestJS Equivalent**: `@PostMapping("/login")` or `@Post('/login')`.

```python
from fastapi import APIRouter
from src.shared.responses import SuccessResponse
from src.modules.auth.schemas import TokenPair

router = APIRouter()

@router.post("/login", response_model=SuccessResponse[TokenPair])
async def login(payload: LoginRequest) -> SuccessResponse[TokenPair]:
    ...
```

### Injection & Validation Annotations (`Depends()`, `Body()`, `Query()`)

* **Purpose**: Configures parameter sources and triggers dependency injection resolution.
* **Spring Boot / NestJS Equivalent**: `@RequestBody`, `@RequestParam`, Constructor Dependency Injection.

```python
from typing import Annotated
from fastapi import Depends, Query
from src.modules.users.service import UserService
from src.modules.users.dependencies import get_user_service

UserServiceDep = Annotated[UserService, Depends(get_user_service)]

@router.get("/users")
async def list_users(
    service: UserServiceDep,                         # Inject service dependency
    limit: Annotated[int, Query(ge=1, le=100)] = 20  # Validate query parameter >= 1 and <= 100
):
    ...
```

### Context Lifespan Decorator (`@asynccontextmanager`)

* **Purpose**: Configures logic to execute before the application starts up, and cleanup tasks to run when the application shuts down.
* **Spring Boot / NestJS Equivalent**: `@PostConstruct` / `@PreDestroy` or `OnApplicationBootstrap` / `BeforeApplicationShutdown` hooks.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: connect to DB/Redis pool
    yield
    # Shutdown logic: clean up connection pools
```

---

## 5. Custom Decorators in Python

Writing custom decorators in Python is straightforward and requires no reflection setup. Use `functools.wraps` to preserve the signature and docstrings of the original function.

### Example: Execution Timer Decorator

```python
import functools
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def time_execution(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that logs the execution duration of a function."""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start_time
        print(f"Function {func.__name__} took {elapsed:.4f} seconds to execute.")
        return result
    return wrapper

# Usage
@time_execution
def heavy_computation(x: int) -> int:
    time.sleep(0.5)
    return x * x
```

---

## 6. Codebase Best Practices: Framework-Agnostic Service Layers

As detailed in the project's developer guide ([AGENTS.md](../../AGENTS.md)), **AsyncPulse enforces a strict separation of concerns**.

### The Rule

**Never import `fastapi`, `Depends`, or raise `HTTPException` inside your service layer files (`service.py`).**

### Why this is critical for Spring Boot / NestJS Developers

In Spring Boot, it is common to sprinkle framework annotations like `@Transactional` or `@Service` directly on your business logic classes. In NestJS, `@Injectable()` and custom decorators are standard in the service layer.

In AsyncPulse, we keep services framework-free for the following reasons:

1. **Testability**: You can test services by passing mock dependencies directly into the constructor (`__init__`) without mocking the FastAPI routing context or injection system.
2. **Decoupling**: If the project transitions from FastAPI to another framework (e.g., Litestar, Django Ninja, or a gRPC server), the service layer's domain logic remains completely untouched.
3. **Clean Exception Handling**: Services raise domain exceptions (e.g., `UserNotFoundError`). Translating these into HTTP statuses is handled globally in `src/core/exception_handlers.py`.

```
HTTP Request → Router (FastAPI Decorators & Depends)
                   ↓
              Service (Pure Python, No Framework imports)
                   ↓
              Repository (SQLAlchemy 2.0 ORM, No FastAPI imports)
```
