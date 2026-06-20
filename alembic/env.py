"""Alembic environment — async-aware, project-integrated."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from src.core.settings import get_settings
from src.db.registry import target_metadata

settings = get_settings()

config = context.config

config.attributes["sqlalchemy.url"] = settings.DATABASE_URL

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def include_name(name: str, type_: str, parent_names: dict) -> bool:
    """Filter schemas — only manage the project schema."""
    if type_ == "schema":
        return name == settings.DB_SCHEMA
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema=settings.DB_SCHEMA,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=settings.DB_SCHEMA,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "server_settings": {
                "search_path": f'"{settings.DB_SCHEMA}",public',
            },
            "statement_cache_size": 0,
        },
    )

    async with connectable.connect() as connection:
        await connection.execute(
            text(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"')
        )
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
