# backend/app/api/v1/api.py
from __future__ import annotations

from fastapi import APIRouter

# REST-/Service-Endpunkte
from app.api.v1.endpoints import (
    auth,
    langgraph_health,
    langgraph_v2,  # LangGraph v2 HTTP/SSE-Endpunkte
    state,
    memory,
    ping,
    users,
    chat_history,  # <-- WICHTIG: Chat-History/Conversations wieder aktivieren
    rag,
)
from app.api.v1.endpoints import rfq as rfq_endpoint

api_router = APIRouter()

# Health / Liveness
api_router.include_router(ping.router)

# Chat History / Conversations (Keycloak-scoped)
api_router.include_router(chat_history.router)  # <-- /api/v1/chat/...

# LangGraph HTTP/SSE-API (v2)
api_router.include_router(langgraph_v2.router, prefix="/langgraph", tags=["langgraph-v2"])
api_router.include_router(langgraph_health.router, prefix="/langgraph", tags=["langgraph-v2"])
api_router.include_router(state.router, prefix="/langgraph", tags=["langgraph-v2"])

# Weitere Subsysteme
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(users.router)
api_router.include_router(rag.router)

# RFQ
api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])
