# backend/app/api/v1/api.py
from __future__ import annotations

from fastapi import APIRouter

# REST-/Service-Endpunkte
from app.api.v1.endpoints import (
    auth,
    langgraph_health,
    langgraph_v2,     # LangGraph v2 HTTP/SSE-Endpunkte
    state,
    memory,
    ping,
    users,
)
from app.api.v1.endpoints import rfq as rfq_endpoint

# WICHTIG:
# - Keine SSE-Registrierung mehr (langgraph_sse entfällt).
# - Kein legacy chat_ws Import/Include mehr.
# - WS-Endpoints werden in ai.py direkt registriert.

api_router = APIRouter()

# Health / Liveness
api_router.include_router(ping.router)

# LangGraph HTTP/SSE-API (v2)
api_router.include_router(langgraph_v2.router, prefix="/langgraph", tags=["langgraph-v2"])
api_router.include_router(langgraph_health.router, prefix="/langgraph", tags=["langgraph-v2"])
api_router.include_router(state.router, prefix="/langgraph", tags=["langgraph-v2"])

# Weitere Subsysteme
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(users.router)

# RFQ
api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])

# NOTE:
# Legacy-Endpunkte (ai/ws + v1 compile-based test invokes) wurden entfernt, da sie alte `app.langgraph.*` Imports ziehen.
# Bitte `/api/v1/langgraph/...` (v2) verwenden.
