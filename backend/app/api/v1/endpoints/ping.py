# backend/app/api/v1/endpoints/ping.py

from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(tags=["health"])


@router.get("/ping")
async def ping() -> dict:
    """
    Sehr einfacher Health-/Liveness-Check.

    Wird von Docker / Nginx als Ping-Endpunkt verwendet.
    """
    return {
        "status": "ok",
        "service": "sealai-backend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
