"""/api/v2/conversations — the M5 memory/history + user-control surface (view / edit / forget).
Every op derives (tenant_id, session_id) ONLY from the verified token — same no-header-trust as chat,
so a tenant's token can never read OR mutate another tenant's memory (P0)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sealai_v2.api.deps import current_identity, get_pipeline
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.pipeline.pipeline import Pipeline

router = APIRouter(prefix="/api/v2/conversations", tags=["conversations"])


def _memory(pipeline: Pipeline):
    if pipeline.memory is None:
        raise HTTPException(status_code=503, detail="memory not enabled")
    return pipeline.memory


@router.get("")
def list_conversations(
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    return {"sessions": list(_memory(pipeline).sessions(tenant_id=identity.tenant_id))}


@router.get("/current/memory")
async def view_memory(
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    mem = _memory(pipeline)
    # P2: a background distill may still be in flight — flush first, so the chips re-fetch
    # right after /chat already sees the fresh case-state (and the history shows the turn).
    await pipeline.flush_memory(
        tenant_id=identity.tenant_id, session_id=identity.session_id
    )
    cs = mem.case_state(tenant_id=identity.tenant_id, session_id=identity.session_id)
    hist = mem.history(tenant_id=identity.tenant_id, session_id=identity.session_id)
    return {
        "case_state": [
            {"feld": f.feld, "wert": f.wert, "provenance": f.provenance} for f in cs
        ],
        "history": [{"role": t.role, "text": t.text} for t in hist],
    }


# Allowlisted fact-edit origins (fail-closed): an inline panel edit (default) vs the parameter form.
# An unrecognized origin is NOT honored — provenance can never be spoofed from the request body.
_EDIT_ORIGINS = {"user-edited", "user-form"}


class FactEdit(BaseModel):
    wert: str
    origin: str | None = (
        None  # "user-form" for the parameter form; else inline panel edit
    )


@router.put("/current/facts/{feld}")
async def edit_fact(
    feld: str,
    body: FactEdit,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    provenance = body.origin if body.origin in _EDIT_ORIGINS else "user-edited"
    mem = _memory(pipeline)
    # P2 flush-then-mutate: a pending distill must land BEFORE the user's write, never after
    # it (the user edit is the stronger, later provenance — it must win).
    await pipeline.flush_memory(
        tenant_id=identity.tenant_id, session_id=identity.session_id
    )
    mem.edit_fact(
        tenant_id=identity.tenant_id,
        session_id=identity.session_id,
        feld=feld,
        wert=body.wert,
        provenance=provenance,
    )
    # M8: a settled input change → recompute + replace the derived slice (no stale kernel value)
    pipeline.recompute_derived_for(
        tenant_id=identity.tenant_id, session_id=identity.session_id
    )
    return {"status": "ok"}


@router.delete("/current/facts/{feld}")
async def forget_fact(
    feld: str,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    mem = _memory(pipeline)
    # P2 flush-then-mutate: the pending distill lands first, then the forget — a late distill
    # must never re-create what the user just deleted.
    await pipeline.flush_memory(
        tenant_id=identity.tenant_id, session_id=identity.session_id
    )
    mem.delete_fact(
        tenant_id=identity.tenant_id, session_id=identity.session_id, feld=feld
    )
    # M8: forgetting a parent input → recompute → its derived child is evicted (no stale value)
    pipeline.recompute_derived_for(
        tenant_id=identity.tenant_id, session_id=identity.session_id
    )
    return {"status": "ok"}


@router.delete("/current")
async def forget_all(
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    mem = _memory(pipeline)
    # P2 flush-then-mutate: "alles vergessen" is final — flush the pending distill, THEN clear.
    await pipeline.flush_memory(
        tenant_id=identity.tenant_id, session_id=identity.session_id
    )
    mem.clear(tenant_id=identity.tenant_id, session_id=identity.session_id)
    return {"status": "ok"}
