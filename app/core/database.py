from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.pool import NullPool
from app.core.config import settings


# DECLARATIVE BASE
class Base(DeclarativeBase):
    pass


# ASYNC ENGINE & SESSION (For FastAPI Routers - Configured for PgBouncer)
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool,  # Delegates connection pooling entirely to PgBouncer
    connect_args={
        "statement_cache_size": 0,  # Required for PgBouncer compatibility
        "prepared_statement_cache_size": 0,
    }
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for async FastAPI endpoints."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# SYNC ENGINE & SESSION (For Video Processing & Background Pipelines)
sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+pg8000://")

sync_engine = create_engine(
    sync_url,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine
)


def get_sync_db() -> Generator[Session, None, None]:
    """Dependency or context manager for synchronous worker tasks."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()