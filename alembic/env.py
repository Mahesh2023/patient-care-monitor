"""Alembic environment (async engine).

On Postgres a session-level advisory lock serialises concurrent migrators,
so several instances booting at once cannot race on DDL.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401  (register tables)
from app.core.db import Base
from src.care_monitor.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
MIGRATION_LOCK_ID = 727_001


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=settings.is_sqlite)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=settings.is_sqlite)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with engine.connect() as conn:
        pg = conn.dialect.name == "postgresql"
        if pg:
            await conn.execute(text(f"SELECT pg_advisory_lock({MIGRATION_LOCK_ID})"))
            await conn.commit()
        try:
            await conn.run_sync(_do_run)
            await conn.commit()
        finally:
            if pg:
                await conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
                await conn.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
