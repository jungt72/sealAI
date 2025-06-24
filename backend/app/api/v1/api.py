# backend/app/api/v1/api.py
from fastapi import APIRouter

# Import aller v1-Endpoints
from .endpoints import (
    ai,
    auth,
    memory,
    users,
    system,
    chat_ws,       # ①  NEW — Web-Socket-Endpoint
)

api_router = APIRouter(prefix="/api/v1")

# REST- und WS-Routen registrieren
api_router.include_router(ai.router,       prefix="/ai")
api_router.include_router(chat_ws.router,  prefix="/ai")   # ②  NEW
api_router.include_router(auth.router,     prefix="/auth")
api_router.include_router(memory.router,   prefix="/memory")
api_router.include_router(users.router,    prefix="/users")
api_router.include_router(system.router,   prefix="/system")
