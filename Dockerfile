# syntax=docker/dockerfile:1

# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: resolve & install dependencies into a venv with uv (locked)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# uv: fast, reproducible installs. Copied from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# 1. Install locked dependencies only (no project code yet) — this layer is
#    cached and only rebuilds when pyproject.toml or uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

# 2. Install the project itself against the resolved environment.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime: minimal image with only the venv and application code
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for the application.
RUN groupadd --system app && useradd --system --gid app --create-home app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy the prebuilt virtualenv and application source from the builder.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src ./src
COPY --from=builder /app/alembic ./alembic
COPY --from=builder /app/alembic.ini ./

USER app

EXPOSE 8000

# Liveness check against the /health endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# Schema is owned by Alembic — run `alembic upgrade head` before/at deploy time,
# not inside this default command (avoids races across multiple replicas).
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
