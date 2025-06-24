# 📁 backend/app/database.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
# Best Practice: Einzige Quelle für Einstellungen ist app.core.config
from app.core.config import settings

# SQLAlchemy Base
Base = declarative_base()

# Datenbank-URL aus Core-Config ziehen
DATABASE_URL = settings.database_url

# Engine mit optionalem SQL-Debug aus den Settings
engine = create_async_engine(
    DATABASE_URL,
    future=True,
    echo=settings.debug_sql,   # gibt SQL-Statements bei Bedarf aus
)

# Session-Factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# FastAPI-Dependency für DB-Sessions
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
