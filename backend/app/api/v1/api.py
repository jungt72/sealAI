# backend/app/api/v1/api.py
from fastapi import APIRouter

# Endpoints
from app.api.v1.endpoints import (
    ai,
    users,
    system,
    chat_ws,
    langgraph_sse,  # besitzt internen Prefix "/langgraph"
    sse_test,
    memory,         # besitzt eigenen Prefix (z. B. "/memory")
    auth,
)

# Optional: nur wenn vorhanden
try:
    from .endpoints import consult_invoke  # type: ignore
except Exception:  # pragma: no cover
    consult_invoke = None  # type: ignore

# Hauptrouter mit einheitlichem API-Prefix
api_router = APIRouter(prefix="/api/v1")

# REST
api_router.include_router(ai.router,       prefix="/ai",    tags=["ai"])
api_router.include_router(auth.router,     prefix="/auth",  tags=["auth"])
api_router.include_router(users.router,    prefix="/users", tags=["users"])
api_router.include_router(system.router,   prefix="/system", tags=["system"])

# Module mit eigenem Prefix nicht doppelt praeﬁxen
api_router.include_router(langgraph_sse.router,            tags=["sse"])
api_router.include_router(memory.router,                   tags=["memory"])
api_router.include_router(sse_test.router, prefix="/debug", tags=["debug"])

# Optionaler Sync-Consult-Test
if consult_invoke:
    api_router.include_router(consult_invoke.router, prefix="/test", tags=["test"])

# WebSocket (z. B. /api/v1/ai/ws, abhängig vom internen Prefix des Moduls)
api_router.include_router(chat_ws.router,                 tags=["ws"])
