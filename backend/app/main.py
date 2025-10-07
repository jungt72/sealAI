# backend/app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# EINZIGE zentrale Router-Aggregation:
# enthält REST, Sync-Debug-Invoke und den WebSocket-Endpunkt unter /api/v1/ai/ws
from app.api.v1.api import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="SealAI Backend",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS – bei Bedarf feiner einstellen (ENV-abhängig)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # z.B. ["https://app.sealai.net"]
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Alle V1-Endpunkte inkl. WebSocket (/api/v1/ai/ws)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()

# Hinweis:
# - Keine Legacy-Imports mehr wie `from app.api.v1.endpoints import chat_ws`
# - Der WebSocket wird ausschließlich in app/api/v1/endpoints/ai.py registriert
# - SSE ist vollständig entfernt
