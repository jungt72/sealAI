# 📁 backend/app/database.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from functools import lru_cache
# Best Practice: Einzige Quelle für Einstellungen ist app.core.config
from app.core.config import settings

# SQLAlchemy Base
Base = declarative_base()

@lru_cache(maxsize=1)
def _get_engine():
    return create_async_engine(
        settings.database_url,
        future=True,
        echo=settings.debug_sql,
    )


@lru_cache(maxsize=1)
def _get_session_factory():
    return sessionmaker(
        bind=_get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


def AsyncSessionLocal():
    return _get_session_factory()()

# FastAPI-Dependency für DB-Sessions
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
