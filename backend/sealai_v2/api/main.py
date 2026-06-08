"""Phase-0 health-only entrypoint for sealai_v2.

A trivial FastAPI app exposing only ``/health`` — no pipeline, no domain logic,
no ``app.*`` imports. This is the container/compose entrypoint
(``sealai_v2.api.main:app``) for the off-by-default ``backend-v2`` service on
port 8001. Real routes (chat/conversations/briefing) arrive in later milestones.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="sealai_v2", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for the Phase-0 scaffold."""
    return {"status": "ok", "service": "sealai_v2"}
