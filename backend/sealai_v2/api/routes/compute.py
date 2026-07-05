"""GET /api/v2/compute — the deterministic kernel READ surface (the Berechnungen panel's source).

Reads the session's CURRENT settled case-state, recomputes the kernel (NO LLM, no L1/L3), PERSISTS
the derived slice (single source with the mutation-channel recompute — so even a missed mutation
channel is corrected on the next read), and returns the kernel result + honest "nicht berechenbar"
reasons. Tenant comes ONLY from the verified token (P0); an optional case_id selects the
same-tenant case. Flush-then-recompute mirrors ``view_memory`` so a pending background distill lands
before the read.

The kernel owns numbers, the browser never computes: this endpoint is the only place the panel's
values come from. 503 fail-closed when compute or memory is disabled (incident kill-switches)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from sealai_v2.api.deps import current_identity, get_pipeline
from sealai_v2.api.serializers import compute_response
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.pipeline.pipeline import Pipeline

router = APIRouter(prefix="/api/v2", tags=["compute"])
CaseIdParam = Annotated[str | None, Query(max_length=255)]


@router.get("/compute")
async def compute(
    case_id: CaseIdParam = None,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    if pipeline.memory is None:
        raise HTTPException(status_code=503, detail="memory not enabled")
    if pipeline.engine is None:
        raise HTTPException(status_code=503, detail="compute not enabled")
    # flush-then-recompute: a pending background distill must land first (mirror view_memory)
    session_id = case_id or identity.session_id
    await pipeline.flush_memory(tenant_id=identity.tenant_id, session_id=session_id)
    comp = pipeline.compute_for(tenant_id=identity.tenant_id, session_id=session_id)
    return compute_response(comp)
