"""Database helpers for LangGraph v2 (reuses app.database AsyncSession)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession using the project's session factory."""
    async with AsyncSessionLocal() as session:  # type: ignore[func-returns-value]
        yield session


__all__ = ["get_db_session"]
