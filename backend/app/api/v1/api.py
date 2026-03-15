# backend/app/api/v1/api.py
from __future__ import annotations

from fastapi import APIRouter

# REST-/Service-Endpunkte
from app.api.v1.endpoints import (
    auth,
    rag,
    langgraph_health,
    memory,
    mcp,
    ping,
    users,
    chat_history,  # <-- WICHTIG: Chat-History/Conversations wieder aktivieren
)
from app.api.v1.endpoints import rfq as rfq_endpoint

api_router = APIRouter()

# Health / Liveness
api_router.include_router(ping.router)

# Chat History / Conversations (Keycloak-scoped)
api_router.include_router(chat_history.router)  # <-- /api/v1/chat/...

# Legacy health endpoint bleibt lesbar, der produktive Chat-/State-Pfad laeuft
# kanonisch ueber /api/agent und wird hier bewusst nicht mehr gemountet.
api_router.include_router(langgraph_health.router, prefix="/langgraph", tags=["health"])

# Model Context Protocol (MCP)
api_router.include_router(mcp.router, prefix="/mcp", tags=["MCP"])

# Weitere Subsysteme
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(users.router)
api_router.include_router(rag.router)

# RFQ
api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])
