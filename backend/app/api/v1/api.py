from __future__ import annotations
from app.api.v1.endpoints import rfq as rfq_endpoint
from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    auth,
    chat_stream,
    chat_ws,
    consult_invoke,
    langgraph_sse,
    memory,
    system,
    users,
    sse_test,        # ⬅️ NEU
)

api_router = APIRouter()

# SSE
api_router.include_router(langgraph_sse.router, prefix="/langgraph", tags=["langgraph"])
api_router.include_router(chat_stream.router, tags=["sse"])
api_router.include_router(sse_test.router, prefix="/sse", tags=["sse"])  # ⬅️ NEU → /api/v1/sse/test

# WebSocket (ohne extra Prefix → /api/v1/ai/ws)
api_router.include_router(chat_ws.router, tags=["ws"])

# Sync-Invoke (Debug)
api_router.include_router(consult_invoke.router, tags=["test"])

# REST
api_router.include_router(ai.router, prefix="/ai")   # ⬅️ Prefix ergänzt → /api/v1/ai/beratung
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(system.router)
api_router.include_router(users.router)

api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])