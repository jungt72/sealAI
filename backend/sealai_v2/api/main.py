"""Entrypoint for sealai_v2 (``sealai_v2.api.main:app``) — the off-by-default ``backend-v2`` service
on port 8001. M6c mounts the real /api/v2 routes (chat / conversations / briefing) as thin projections
over the pure ``sealai_v2`` core; identity is derived ONLY from a verified token inside V2 (no
``app.*`` imports). The V1 runtime is separate and untouched.
"""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from sealai_v2.api.routes import (
    anfrage,
    briefing,
    chat,
    compute,
    contribute,
    conversations,
    framing,
    hersteller,
    legal,
    memory_v2,
    partner_self,
    rag_ingest,
)
from sealai_v2.config.settings import Settings
from sealai_v2.pipeline.timing import configure_timing_logging

configure_timing_logging()  # per-turn timing lines → stdout (visible in docker logs)
app = FastAPI(title="sealai_v2", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(briefing.router)
app.include_router(compute.router)
app.include_router(framing.router)
app.include_router(legal.router)
app.include_router(anfrage.router)
app.include_router(hersteller.router)
app.include_router(partner_self.router)
app.include_router(contribute.router)
app.include_router(rag_ingest.router)
app.include_router(memory_v2.router)
if Settings().metrics_enabled:
    Instrumentator(
        excluded_handlers=["/health", "/api/v2/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/health")
@app.get("/api/v2/health")
async def health() -> dict[str, str]:
    """Liveness probe — also under /api/v2/ because the nginx proxy preserves the path."""
    return {"status": "ok", "service": "sealai_v2"}
