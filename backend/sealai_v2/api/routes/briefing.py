"""POST /api/v2/briefing — read-only projection of one explicit authorized case revision."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from sealai_v2.api.deps import (
    get_pipeline,
    require_legal_acceptance,
)
from sealai_v2.api.case_artifacts import project_briefing
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.engine import bind_database_case
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.render.renderer import ArtifactRenderer

router = APIRouter(prefix="/api/v2", tags=["briefing"])
_renderer = ArtifactRenderer()


class BriefingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._~-]+$")
    case_revision: int = Field(ge=0)


@router.post("/briefing")
async def briefing(
    req: BriefingRequest,
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    with bind_database_case(req.case_id):
        snapshot, art = await project_briefing(
            pipeline=pipeline,
            identity=identity,
            case_id=req.case_id,
            case_revision=req.case_revision,
            renderer=_renderer,
        )
    return {
        "kind": art.kind,
        "title": art.title,
        "body": art.body,
        "provenance": list(art.provenance),
        "wissensstand": art.wissensstand,
        # Legal-by-Design Phase D (Goal 6/9): drives the PDF export's warning badge
        # (frontend-v2/src/lib/pdf.ts) — same signal as the chat response's risk_flags.
        "risk_flags": list(art.risk_flags),
        "case_id": snapshot.case_id,
        "case_revision": snapshot.case_revision,
        "message_index": snapshot.message_index,
        "read_only": True,
    }
