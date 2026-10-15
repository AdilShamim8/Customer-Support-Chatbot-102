"""
src/database/connection.py — Database Connection and Session Management for the Customer Support Chatbot
Current setup has no connection pool configuration.
Under load, this causes connection exhaustion.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, QueuePool

from configs.settings import settings

logger = structlog.get_logger(__name__)


def create_engine(database_url: str):
    """
    Create SQLAlchemy async engine with production-grade pool config.
    """
    if settings.is_development:
        # Development: smaller pool, echo SQL
        return create_async_engine(
            database_url,
            echo=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,   # Validate connections before use
        )
    else:
        # Production: larger pool, no SQL echo
        return create_async_engine(
            database_url,
            echo=False,
            pool_size=20,
            max_overflow=40,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            connect_args={
                "command_timeout": 10,
                "server_settings": {
                    "application_name": "customer-support-chatbot",
                },
            },
        )


engine = create_engine(settings.database_url)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    Async context manager for database sessions.
    Handles commit, rollback, and cleanup automatically.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for database session."""
    async with get_db_session() as session:
        yield session


async def check_db_health() -> bool:
    """Check database connectivity for health endpoint."""
    try:
        async with get_db_session() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return False