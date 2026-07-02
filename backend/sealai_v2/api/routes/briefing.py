"""POST /api/v2/briefing — the M4b deterministic render projected over a pipeline run. Tenant +
session from the verified token only (P0). The render never touches L1/L3 (no behavior change)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    current_identity,
    flags_from_settings,
    get_pipeline,
    get_settings,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import SessionContext, VerifiedIdentity
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.render.renderer import ArtifactRenderer, snapshot_from_result
from sealai_v2.security.tenant import TenantContext

router = APIRouter(prefix="/api/v2", tags=["briefing"])
_renderer = ArtifactRenderer()


class BriefingRequest(BaseModel):
    message: str = Field(min_length=1)


@router.post("/briefing")
async def briefing(
    req: BriefingRequest,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = await pipeline.run(
        req.message,
        tenant=TenantContext(identity.tenant_id),
        session=SessionContext(session_id=identity.session_id),
        flags=flags_from_settings(settings),
    )
    art = _renderer.briefing(snapshot_from_result(req.message, result))
    return {
        "kind": art.kind,
        "title": art.title,
        "body": art.body,
        "provenance": list(art.provenance),
        "wissensstand": art.wissensstand,
    }
