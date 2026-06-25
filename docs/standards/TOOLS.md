# Tools & Libraries

This document catalogs every tool and library used to build, test, lint, and
maintain AsyncPulse, with installation, configuration, and usage for each. Pin
versions in `pyproject.toml`; do not rely on globally installed tools.

> Source of truth for tool config is `pyproject.toml`, and for commands the
> `Makefile`. Where this doc and those files disagree, those files win — update
> this doc to match.

---

## 1. Runtime & Framework

| Tool               | Purpose                    | Notes                                            |
| ------------------ | -------------------------- | ------------------------------------------------ |
| **Python 3.12+**   | Runtime                    | `requires-python = ">=3.12"` in `pyproject.toml` |
| **FastAPI**        | ASGI web framework         | Routes, DI, OpenAPI docs                         |
| **Uvicorn**        | ASGI server                | `uvicorn[standard]` for uvloop + httptools       |
| **Pydantic v2**    | Data validation & settings | `pydantic[email]` + `pydantic-settings`          |
| **SQLAlchemy 2.0** | ORM (async)                | `sqlalchemy[asyncio]`, 2.0-style `select()`      |
| **asyncpg**        | PostgreSQL async driver    | Production database driver                       |
| **aiosqlite**      | SQLite async driver        | Development / testing fallback                   |
| **Alembic**        | Database migrations        | Autogenerate from SQLAlchemy models              |

---

## 2. Authentication & Security

| Tool                 | Purpose                                                   |
| -------------------- | --------------------------------------------------------- |
| **python-jose**      | JWT creation & verification (`python-jose[cryptography]`) |
| **bcrypt**           | Password hashing                                          |
| **python-multipart** | Form parsing (required by the OAuth2 password flow)       |

---

## 3. Background Jobs & Caching

| Tool      | Purpose                                                           |
| --------- | ----------------------------------------------------------------- |
| **redis** | Redis client, used as the cache layer (RTR sessions, user cache)  |
| **arq**   | Redis-backed async job queue _(planned; not yet in dependencies)_ |

> Note: `arq` is referenced in the architecture docs as the intended worker
> queue but is **not** currently listed in `pyproject.toml`. Add it before
> implementing workers.

---

## 4. Observability

| Tool                  | Purpose                         | Notes                                        |
| --------------------- | ------------------------------- | -------------------------------------------- |
| **structlog**         | Structured logging              | Module-level singleton in `shared/logger.py` |
| **prometheus-client** | Metrics _(planned)_             | Not yet a dependency                         |
| **OpenTelemetry**     | Distributed tracing _(planned)_ | Not yet a dependency                         |

> Only `structlog` is currently installed. `prometheus-client` and
> OpenTelemetry are part of the target design but are not yet in
> `pyproject.toml`.

---

## 5. Linting & Formatting — Ruff

Ruff is the single tool for both **linting and formatting**. The project does
**not** use `black`, `flake8`, `isort`, `autopep8`, or `pycodestyle` — Ruff
replaces all of them.

Install (included in the `dev` and `lint` groups):

```bash
pip install -e ".[lint]"        # or: uv sync --extra lint
```

Usage:

```bash
ruff format src/ tests/         # format in place (Black-style)
ruff check src/ tests/          # lint, check-only (CI)
ruff check --fix src/ tests/    # lint + auto-fix
```

Makefile shortcuts:

```bash
make format     # ruff format + ruff check --fix
make lint       # ruff check (check-only)
```

Config: `[tool.ruff]` in `pyproject.toml`. Key settings:

- `target-version = "py312"`, `line-length = 100`
- `[tool.ruff.format]`: `quote-style = "double"`, `indent-style = "space"`
- Enabled rule sets: `E`, `W`, `F`, `I`, `N`, `UP`, `S`, `B`, `A`, `C4`, `SIM`,
  `TC`, `RUF`, `ANN`, `D` (pydocstyle, `pep257` convention)
- Tests relax `S101` (asserts) and `ANN` (annotations) via per-file-ignores

---

## 6. Type Checking

The project uses **two** type checkers with distinct roles. Pyright is the
authoritative checker for the CLI/CI; ty is an optional fast editor LSP.

### Pyright — authoritative (CLI & CI)

This is what `make typecheck` runs and what gates CI. It is installed via the
`dev`/`lint` dependency groups and configured in strict mode.

```bash
pyright src/        # or: make typecheck
```

Config: `[tool.pyright]` in `pyproject.toml`. Key settings:

- `typeCheckingMode = "strict"`
- `include = ["src"]`, `extraPaths = ["."]`
- `venvPath = "."`, `venv = ".venv"`
- `reportUnnecessaryTypeIgnoreComment = true`

### ty (Astral) — editor LSP (preview)

`ty` is Astral's Rust-based type checker / language server (same family as Ruff
and uv). It is currently used **only as the in-editor type checker on non-VS Code
IDEs** (installed as an editor extension — see §9). It is **not** in the project
dependencies, is **not** wired into the `Makefile`, and does **not** gate CI.

- The editor extension **bundles its own `ty` binary**, so no project dependency
  change is required to use it in the editor.
- `ty` is in **beta** (stable 1.0 targeted for 2026); its diagnostics still
  differ from Pyright's. Treat it as fast live feedback, not the source of truth.

Optional CLI use (only if you want to run it outside the editor):

```bash
uvx ty check src/               # run ad hoc without installing into the project
# or pin it as a dependency:
uv add --optional lint ty       # then: ty check src/
```

> Migration note: ty is intentionally **not** the project's primary checker yet.
> Revisit promoting it (adding to `lint`, adding a `make typecheck-ty` target,
> or replacing pyright) once it reaches a stable 1.0 and its findings have been
> compared against Pyright on this codebase.

---

## 7. Testing

| Tool               | Purpose                            | Notes                                  |
| ------------------ | ---------------------------------- | -------------------------------------- |
| **pytest**         | Test runner                        | `asyncio_mode = "auto"`                |
| **pytest-asyncio** | Async test support                 | Default fixture loop scope: `function` |
| **httpx**          | Async HTTP client for router tests | `AsyncClient` over the ASGI app        |
| **aiosqlite**      | In-memory/file SQLite for tests    | In the `test` group                    |

Install + run:

```bash
pip install -e ".[test]"        # or: uv sync --extra test
pytest tests/ -v --tb=short             # make test
pytest tests/ -v --tb=short --cov=src --cov-report=term-missing   # make test-cov
```

Test layout mirrors the module structure: `tests/modules/<feature>/`.

---

## 8. Dependency Management

The project standardizes on **uv** (Astral's Rust-based resolver/installer) with
**pip** as a fallback. A committed `uv.lock` is the lockfile.

| Tool    | Purpose                                                         |
| ------- | --------------------------------------------------------------- |
| **uv**  | Primary dependency resolver & installer; `uv.lock` is committed |
| **pip** | Fallback installer for environments without uv                  |

Common commands:

```bash
# uv (preferred)
uv sync                          # install from uv.lock
uv sync --extra dev              # install with the dev group
uv add <package>                 # add a runtime dependency
uv add --optional dev <package>  # add to the dev group

# pip (fallback)
pip install -e ".[dev,test,lint]"
```

Dependency groups in `pyproject.toml` (`[project.optional-dependencies]`):

- `dependencies` — production runtime
- `dev` — pytest, pytest-asyncio, httpx, ruff, pyright
- `test` — pytest, pytest-asyncio, httpx, aiosqlite
- `lint` — ruff, pyright

> `requirements.txt` is a partial pinned export for environments that need it;
> `uv.lock` + `pyproject.toml` remain the source of truth.

---

## 9. IDE Setup (Non-VS Code Editors)

For VS Code forks that pull extensions from **Open VSX** (Kiro, Cursor,
Antigravity, etc.):

| Extension       | ID                   | Purpose                                          |
| --------------- | -------------------- | ------------------------------------------------ |
| **ty** (Astral) | `astral-sh.ty`       | Fast type-checking LSP (first-party on Open VSX) |
| **Ruff**        | `charliermarsh.ruff` | Linting + formatting                             |
| **Python**      | `ms-python.python`   | Core Python support (ty depends on this)         |

Notes:

- **Pylance is unavailable** outside official VS Code — it is proprietary and
  Microsoft does not publish it to Open VSX.
- Avoid the mirrored `ms-pyright.pyright` on Open VSX: it is a stale community
  mirror (published by the Open VSX bot, not Microsoft), often a release behind.
  If you want a Pyright-based LSP in-editor that matches CI, prefer
  **BasedPyright** (`detachhead.basedpyright`).
- Install only **one** type-checking LSP to avoid duplicate diagnostics.

---

## 10. Makefile Targets

| Command                     | Runs        | Description                       |
| --------------------------- | ----------- | --------------------------------- |
| `make format`               | ruff        | Format + auto-fix                 |
| `make lint`                 | ruff        | Lint, check-only                  |
| `make typecheck`            | **pyright** | Strict type check (authoritative) |
| `make test`                 | pytest      | Run tests                         |
| `make test-cov`             | pytest      | Tests + coverage report           |
| `make run`                  | uvicorn     | Dev server with `--reload`        |
| `make clean`                | —           | Remove caches and build artifacts |
| `make migrate-gen m="desc"` | alembic     | Generate a migration              |
| `make migrate-up`           | alembic     | Apply all pending migrations      |
| `make migrate-down`         | alembic     | Roll back the last migration      |
| `make migrate-history`      | alembic     | Show migration history            |
| `make migrate-current`      | alembic     | Show current migration revision   |

---

## 11. Pre-Commit / Pre-Push Workflow

Run before committing:

```bash
make format        # ruff format + auto-fix
make lint          # ruff check
make typecheck     # pyright (authoritative)
make test          # pytest
```

CI should run `lint`, `typecheck`, and `test` as separate steps. `ty` is not
part of this gate while it is in beta; use it in your editor for faster feedback.
