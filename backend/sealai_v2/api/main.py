"""Entrypoint for sealai_v2 (``sealai_v2.api.main:app``) — the off-by-default ``backend-v2`` service
on port 8001. M6c mounts the real /api/v2 routes (chat / conversations / briefing) as thin projections
over the pure ``sealai_v2`` core; identity is derived ONLY from a verified token inside V2 (no
``app.*`` imports). The V1 runtime is separate and untouched.
"""

from __future__ import annotations

from fastapi import FastAPI

from sealai_v2.api.routes import briefing, chat, conversations

app = FastAPI(title="sealai_v2", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(briefing.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "sealai_v2"}
