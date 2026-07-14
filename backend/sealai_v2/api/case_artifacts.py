"""Read-only, owner-bound artifact projection from one exact conversation revision."""

from __future__ import annotations

from fastapi import HTTPException

from sealai_v2.core.contracts import (
    ArtifactCaseSnapshot,
    CaseRevisionConflict,
    ConversationAccessDenied,
    RenderSnapshot,
    VerifiedIdentity,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.render.renderer import ArtifactRenderer
from sealai_v2.safety.risk_flags import detect_risk_flags


async def project_briefing(
    *,
    pipeline: Pipeline,
    identity: VerifiedIdentity,
    case_id: str,
    case_revision: int,
    renderer: ArtifactRenderer,
):
    """Return an immutable case snapshot plus its deterministic briefing.

    Flush only completes work already scheduled by the prior chat request. This function never runs
    L1/L3, records a turn, merges a fact, or trusts client-supplied message text.
    """

    if pipeline.memory is None:
        raise HTTPException(
            status_code=503, detail="authoritative case store unavailable"
        )
    try:
        # Authorize before touching even pre-existing background work for this case.  The
        # subsequent snapshot repeats the owner check after the flush, so a concurrent ownership
        # or revision change still fails closed.
        pipeline.memory.assert_session_access(
            tenant_id=identity.tenant_id,
            session_id=case_id,
            owner_subject=identity.subject,
        )
        await pipeline.flush_memory(tenant_id=identity.tenant_id, session_id=case_id)
        snapshot: ArtifactCaseSnapshot = pipeline.memory.artifact_snapshot(
            tenant_id=identity.tenant_id,
            session_id=case_id,
            owner_subject=identity.subject,
            expected_case_revision=case_revision,
        )
    except ConversationAccessDenied as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except CaseRevisionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "case_revision_changed",
                "message": "Der Fall wurde geändert; bitte den aktuellen Stand neu laden.",
            },
        ) from exc
    artifact = renderer.briefing(
        RenderSnapshot(
            question=snapshot.question,
            answer_text=snapshot.answer,
            risk_flags=detect_risk_flags(snapshot.question),
        )
    )
    return snapshot, artifact
