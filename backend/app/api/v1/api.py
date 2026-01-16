# backend/app/api/v1/api.py
from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# REST-/Service-Endpunkte
from app.api.v1.endpoints import (  # noqa: E402
    auth,
    langgraph_health,
    langgraph_v2,  # LangGraph v2 HTTP/SSE-Endpunkte
    state,
    memory,
    ping,
    users,
    rag,
)
from app.api.v1.endpoints import rfq as rfq_endpoint  # noqa: E402

api_router = APIRouter()

# Health / Liveness
api_router.include_router(ping.router)

# --- Chat History / Conversations (Keycloak-scoped) ---------------------------
# Hardening: chat_history kann in der Vergangenheit überschrieben/umgebaut worden sein
# (z.B. Tool-only Modul ohne APIRouter). Das darf den Backend-Start nicht mehr killen.
try:
    from app.api.v1.endpoints import chat_history  # noqa: E402

    router = getattr(chat_history, "router", None)
    if router is None:
        logger.warning(
            "chat_history endpoint loaded but has no `router` attribute; skipping include_router",
            extra={"module": "app.api.v1.endpoints.chat_history"},
        )
    else:
        api_router.include_router(router)  # /api/v1/chat/...
except Exception as exc:  # pragma: no cover
    logger.warning(
        "Failed to import/include chat_history router; continuing without chat history endpoints: %s",
        exc,
        extra={"module": "app.api.v1.endpoints.chat_history"},
    )

# --- LangGraph HTTP/SSE-API (v2) ---------------------------------------------
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
