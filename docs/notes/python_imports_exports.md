# Python Imports, Exports, and Dynamic Resolution

This document explains Python's import execution model, public module exports via the `__all__` dunder variable, and dynamic name resolution (reflection) using `globals()` and `getattr()`.

---

## 1. How Python Imports Work

In Python, importing a module is **not** just loading a reference—**it is an execution**.

When Python runs `import my_module` or `from my_module import my_variable`:

1. It checks if the module has already been imported in `sys.modules`. If yes, it retrieves the cached module.
2. If it is the first import, Python **executes every line of code** inside `my_module.py` from top to bottom.
3. Any functions, classes, and variables defined during this execution are stored in the module's namespace dictionary.

### The Database Registry Pattern Example

In SQLAlchemy, models register themselves with the declarative base when Python compiles their class definition. This is why [registry.py](../../src/db/registry.py) imports all models, despite never calling them:

```python
# registry.py
from src.db.base import Base

# Importing these files runs their code, which registers them with Base.metadata:
from src.modules.auth.models import SessionModel
from src.modules.users.models import UserModel

target_metadata = Base.metadata
```

Without these imports, Python would never run those files during Alembic migrations, resulting in an empty `Base.metadata`.

---

## 2. The `__all__` Dunder Variable

`__all__` is a special module-level variable that defines the public interface of a Python module.

### Why is it a list of Strings?

Python's import system resolves names by looking them up as string keys in the module's namespace dictionary (`globals()`). Therefore, `__all__` must contain string literals representing the names of the exports, rather than direct references to the objects themselves.

```python
# ✅ CORRECT: List of strings
__all__ = ["SessionModel", "UserModel", "target_metadata"]

# ❌ INCORRECT: List of direct references (leads to Syntax or Type errors on wildcard import)
__all__ = [SessionModel, UserModel, target_metadata]
```

### The Roles of `__all__`

#### A. Controlling Wildcard Imports (`*`)

If someone performs a wildcard import, only the names listed in `__all__` will be imported:

```python
# client.py
from src.db.registry import *

# Only SessionModel, UserModel, and target_metadata are imported.
# Internal imports like 'Base' (which registry.py imported) are ignored.
```

#### B. Silencing Linter "Unused Import" Warnings (e.g., F401)

Linters like Ruff or Pyright flags unused imports as errors:
`F401: 'UserModel' imported but unused.`

By placing `"UserModel"` in `__all__`, you tell the linter that the import is intended for re-export, silencing the warning.

---

## 3. Dynamic Name Resolution (Reflection)

Since Python is a dynamic language, you can look up variables or attributes using strings at runtime.

### A. Accessing Globals dynamically via `globals()`

Every module has a `globals()` dictionary holding all variables defined in that module's scope.

```python
import math

# We have the function name as a string
func_name = "sqrt"

# Retrieve the function dynamically from the math module's namespace
math_globals = math.__dict__
sqrt_func = math_globals[func_name]

print(sqrt_func(16))  # Prints: 4.0
```

### B. Accessing Object Attributes via `getattr()`

`getattr(object, name)` retrieves an attribute or method from an object using its string name.

```python
class User:
    def __init__(self, email: str, name: str):
        self.email = email
        self.name = name

user = User("alex@example.com", "Alex")

# Retrieve attribute dynamically
attribute_to_get = "email"
email_val = getattr(user, attribute_to_get)
print(email_val)  # Prints: "alex@example.com"
```

---

## 4. Practical Runnable Example

Create a file named `dynamic_demo.py` and run it to see these concepts in action:

```python
# dynamic_demo.py

# 1. Define exports
__all__ = ["greet", "SUPPORTED_LANGUAGES"]

SUPPORTED_LANGUAGES = ["en", "es", "fr"]
secret_key = "super-secret"  # Private variable (not in __all__)

def greet(name: str) -> str:
    return f"Hello, {name}!"

# 2. Dynamic Attribute access demo
class Configuration:
    def __init__(self):
        self.db_host = "localhost"
        self.db_port = 5432

if __name__ == "__main__":
    config = Configuration()

    # Read variables dynamically
    for setting in ["db_host", "db_port"]:
        value = getattr(config, setting)
        print(f"Setting {setting} has value: {value}")

    # Look up functions dynamically using globals()
    function_to_call = "greet"
    func = globals()[function_to_call]
    print(func("Antigravity"))  # Prints: Hello, Antigravity!
```
