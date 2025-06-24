# 📁 backend/app/api/dependencies.py

from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db():
    db: AsyncSession = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()

# Optional: Auth-Helper
def get_current_username(token) -> str:
    from app.services.auth.jwt_utils import extract_username_from_token
    return extract_username_from_token(token.credentials)
