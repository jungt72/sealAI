# backend/app/api/v1/api.py

from fastapi import APIRouter

# Import aller v1-Endpoints
from .endpoints import (
    auth,
    memory,
    users,
    system,
    chat_ws,
    ai,
)

api_router = APIRouter(prefix="/api/v1")

# WebSocket-Endpoint für AI-Chat als erstes registrieren
api_router.include_router(chat_ws.router, prefix="/ai")

# REST-Endpoints unter demselben /ai-Prefix (falls nötig)
api_router.include_router(ai.router,     prefix="/ai")

# Die übrigen REST-Endpoints
api_router.include_router(auth.router,   prefix="/auth")
api_router.include_router(memory.router, prefix="/memory")
api_router.include_router(users.router,  prefix="/users")
api_router.include_router(system.router, prefix="/system")
