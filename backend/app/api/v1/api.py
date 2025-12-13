# backend/app/api/v1/api.py
from __future__ import annotations

from fastapi import APIRouter

# REST-/Service-Endpunkte
from app.api.v1.endpoints import (
    ai,               # → enthält WS (/api/v1/ai/ws) + Sync-Invoke (/api/v1/ai/beratung)
    auth,
    consult_invoke,   # optionaler Sync-Debug-Invoke
    langgraph_v2,     # LangGraph v2 HTTP/SSE-Endpunkte
    memory,
    system,
    users,
)
from app.api.v1.endpoints import rfq as rfq_endpoint

# WICHTIG:
# - Keine SSE-Registrierung mehr (langgraph_sse entfällt).
# - Kein legacy chat_ws Import/Include mehr.
# - WS-Endpoints werden in ai.py direkt registriert.

api_router = APIRouter()

# AI (WS+Sync)
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])

# Optional: Debug/Test invoke
api_router.include_router(consult_invoke.router, tags=["test"])

# LangGraph HTTP/SSE-API (v2)
api_router.include_router(langgraph_v2.router, prefix="/langgraph", tags=["langgraph-v2"])

# Weitere Subsysteme
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(system.router)
api_router.include_router(users.router)

# RFQ
api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])
