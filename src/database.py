"""Database session management and Redis client."""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

# SQLAlchemy async engine — replace psycopg with psycopg_async driver
_async_url = settings.DATABASE_URL.replace(
    "postgresql+psycopg://", "postgresql+psycopg_async://"
)
engine = create_async_engine(_async_url, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Redis async client
redis_client = aioredis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)
