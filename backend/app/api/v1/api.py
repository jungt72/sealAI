# backend/app/api/v1/api.py
from __future__ import annotations

from fastapi import APIRouter

# REST-/Service-Endpunkte
from app.api.v1.endpoints import (
    auth,
    langgraph_health,
    langgraph_v2,
    memory,
    ping,
    users,
    chat_history,  # <-- WICHTIG: Chat-History/Conversations wieder aktivieren
    rag,
    mcp,
    state,
)
from app.api.v1.endpoints import rfq as rfq_endpoint

api_router = APIRouter()

# Health / Liveness
api_router.include_router(ping.router)

# Chat History / Conversations (Keycloak-scoped)
api_router.include_router(chat_history.router)  # <-- /api/v1/chat/...

# [DEPRECATED — Phase F-A.5 / residual compat only] Legacy LangGraph HTTP/SSE-API (v2)
# The router stays mounted for narrow compatibility and health inspection only.
# Productive chat authority lives on /api/agent; the compat chat facade is
# opt-in inside langgraph_v2.py and disabled by default.
api_router.include_router(langgraph_health.router, prefix="/langgraph", tags=["health"])
api_router.include_router(langgraph_v2.router, prefix="/langgraph", tags=["langgraph"])
api_router.include_router(state.router, tags=["state"])

# Model Context Protocol (MCP)
api_router.include_router(mcp.router, prefix="/mcp", tags=["MCP"])

# Weitere Subsysteme
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(users.router)
api_router.include_router(rag.router)

# RFQ
api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])

# Agent canonical path: /api/agent (mounted in main.py — Phase F-A.5).
# Single canonical mount. No secondary /api/v1/agent path.
