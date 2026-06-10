"""GET /api/v2/framing — the safety-framing texts (cutover Phase 1a). PUBLIC by design: static
liability wording with zero tenant data, and the SPA must render it pre-login and during auth
outages — so this route deliberately has NO ``current_identity`` dependency (the documented
exception to the fail-closed /api/v2 default). Source of truth: ``sealai_v2.core.framing``."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from sealai_v2.core.framing import framing_payload

router = APIRouter(prefix="/api/v2", tags=["framing"])


@router.get("/framing")
async def framing() -> JSONResponse:
    # Short public TTL: a framing-text change (lawyer revision) propagates within minutes.
    return JSONResponse(
        content=framing_payload(), headers={"Cache-Control": "public, max-age=300"}
    )
