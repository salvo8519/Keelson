"""Async PostgreSQL sessions (Keelson: two logins, see app/db/tenancy.py).

* ``get_db_session`` / ``get_db_context``: the **application login**, under row level
  security. Every transaction states the request's principal (user, organization or API key);
  without one it sees nothing.
* ``system_session(reason)``: the **owner login**, for work that has no user yet or spans
  tenants (sign-in, lookups by token, the platform administration, the command line). Each use
  is logged with its reason, so privileged access is visible in the logs and in review.
* ``get_worker_db_context``: the owner login for background workers, which act across
  organizations by design.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)
system_logger = logging.getLogger("app.db.system")

# Marks the sessions of the application login; read by the listener in app/db/tenancy.py.
REQUEST_SESSION = "keelson_request"


def _engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
    )


# Requests: the application login.
engine = _engine(settings.APP_DATABASE_URL)
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, info={REQUEST_SESSION: True}
)

# System work: the owner login.
system_engine = _engine(settings.DATABASE_URL)
system_session_maker = async_sessionmaker(system_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def _managed_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Shared session lifecycle: commit on success, rollback on error."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except AppException:
            # An expected outcome (not found, forbidden, conflict): undo, no error log.
            await session.rollback()
            raise
        except Exception:
            logger.exception("DB session error, rolling back")
            try:
                await session.rollback()
            except Exception:
                logger.exception("DB session rollback failed")
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Session of the application login, for FastAPI dependencies."""
    async with _managed_session(async_session_maker) as session:
        yield session


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Session of the application login, as a context manager (WebSockets, agent turns)."""
    async with _managed_session(async_session_maker) as session:
        yield session


@asynccontextmanager
async def system_session(reason: str) -> AsyncGenerator[AsyncSession, None]:
    """Session of the owner login, outside row level security. ``reason`` is logged."""
    system_logger.info("system session: %s", reason, extra={"reason": reason})
    async with _managed_session(system_session_maker) as session:
        yield session


@asynccontextmanager
async def get_worker_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get a short-lived owner session for background workers (Celery/Taskiq/ARQ).

    Creates a fresh engine with NullPool on every call so there are no
    cross-fork / cross-event-loop connection issues.  The engine is disposed
    automatically when the context manager exits.
    """
    worker_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except AppException:
            # An expected outcome (not found, forbidden, conflict): undo, no error log.
            await session.rollback()
            raise
        except Exception:
            logger.exception("DB session error, rolling back")
            try:
                await session.rollback()
            except Exception:
                logger.exception("DB session rollback failed")
            raise
        finally:
            await worker_engine.dispose()


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    await system_engine.dispose()
