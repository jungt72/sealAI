# backend/app/api/routes/health.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])

@router.get("/ping")
async def ping():
    """
    Healthcheck für Docker Compose (siehe docker-compose.yml).
    Gibt 200 OK zurück, wenn Backend lauffähig ist.
    """
    return {"status": "ok", "service": "sealai-backend"}
