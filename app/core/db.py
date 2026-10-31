"""Async SQLAlchemy engine / session factory.

Postgres (asyncpg) in production, SQLite (aiosqlite) for local dev & tests.
Pool sizing is per worker process: total connections =
    instances x WEB_CONCURRENCY x (pool_size + max_overflow)
Keep that below the Postgres plan's connection limit (or front with PgBouncer).
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.care_monitor.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_timeout": 10,
    }


engine = create_async_engine(settings.database_url, **_engine_kwargs())

if settings.is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_fk(dbapi_conn, _):  # enforce ON DELETE CASCADE like Postgres
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
