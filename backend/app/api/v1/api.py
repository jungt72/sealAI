from __future__ import annotations
from app.api.v1.endpoints import rfq as rfq_endpoint
from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    auth,
    chat_ws,
    consult_invoke,
    memory,
    system,
    users,
)
from app.api.v1.endpoints import langgraph_sse  # <-- NEU

api_router = APIRouter()

# SSE
api_router.include_router(langgraph_sse.router, prefix="/langgraph", tags=["sse"])  # <-- NEU

# WebSocket (ohne extra Prefix → /api/v1/ai/ws)
api_router.include_router(chat_ws.router, tags=["ws"])

# Sync-Invoke (Debug)
api_router.include_router(consult_invoke.router, tags=["test"])

# REST
api_router.include_router(ai.router, prefix="/ai")   # → /api/v1/ai/beratung
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(system.router)
api_router.include_router(users.router)

api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])
