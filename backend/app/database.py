from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Engines are created on first access to avoid import-time failures when the
# database driver is not installed (e.g. in unit test environments that use
# SQLite / aiosqlite instead of asyncpg / psycopg2).
# ---------------------------------------------------------------------------

_async_engine = None
_sync_engine = None
_AsyncSessionLocal = None
_SyncSessionLocal = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _async_engine


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.SYNC_DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _sync_engine


def _get_async_session_factory():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            bind=_get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _AsyncSessionLocal


def _get_sync_session_factory():
    global _SyncSessionLocal
    if _SyncSessionLocal is None:
        _SyncSessionLocal = sessionmaker(
            bind=_get_sync_engine(),
            autoflush=False,
            autocommit=False,
        )
    return _SyncSessionLocal


# Module-level callable aliases – engines/factories are created lazily on first
# call to avoid import-time failures when the DB driver is not installed.
async_engine = _get_async_engine
AsyncSessionLocal = _get_async_session_factory
sync_engine = _get_sync_engine
SyncSessionLocal = _get_sync_session_factory


async def get_async_db() -> AsyncSession:  # type: ignore[return]
    async with _get_async_session_factory()() as session:
        yield session


def get_sync_db():
    factory = _get_sync_session_factory()
    db: Session = factory()
    try:
        yield db
    finally:
        db.close()
