"""/api/v2/conversations — the M5 memory/history + user-control surface (view / edit / forget).
``tenant_id`` ALWAYS derives from the verified token (P0 — a tenant's token can never read or
mutate another tenant's memory, no exceptions). The effective session, in contrast, is now an
OPTIONAL client-supplied ``case_id`` override ("Fälle"-Sidebar, Patch A): every route below falls
back to ``identity.session_id`` (today's sole behavior) when ``case_id`` is absent — byte-identical
for any caller that doesn't opt in. A ``case_id`` for a session that doesn't exist (wrong tenant, or
simply never created) resolves to an empty/no-op read, never a leak — the ``(tenant_id, case_id)``
tuple then matches no row, the exact same "fresh session" behavior an unused ``session_id`` already
has today."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from sealai_v2.api.confirmation import build_param_confirmation
from sealai_v2.api.deps import current_identity, get_pipeline
from sealai_v2.api.serializers import compute_response
from sealai_v2.core.calc.derived import recompute_derived
from sealai_v2.core.contracts import (
    ConversationAccessDenied,
    RememberedFact,
    VerifiedIdentity,
)
from sealai_v2.pipeline.pipeline import Pipeline

router = APIRouter(prefix="/api/v2/conversations", tags=["conversations"])

# Same width as V2Session.session_id (db/models.py) — an over-long case_id now fails closed with a
# clean 422 instead of a generic 500 surfaced from the DB column's own length constraint.
CaseIdParam = Annotated[str | None, Query(max_length=255)]


def _memory(pipeline: Pipeline):
    if pipeline.memory is None:
        raise HTTPException(status_code=503, detail="memory not enabled")
    return pipeline.memory


def _require_session_access(mem, identity: VerifiedIdentity, session_id: str) -> None:
    try:
        mem.assert_session_access(
            tenant_id=identity.tenant_id,
            session_id=session_id,
            owner_subject=identity.subject,
        )
    except ConversationAccessDenied as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc


@router.get("")
async def list_conversations(
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    # P2 flush-then-read (same discipline as every other route in this file): a background
    # remember from the turn the user JUST sent may still be in flight — without this, a brand
    # new case's very first message could resolve, return the answer, and the case list
    # (re-fetched by the frontend right after) would still show "keine Fälle", since the
    # V2Session row record_turn creates hadn't landed yet. Flushes ALL of this tenant's pending
    # remembers (not one session_id) because this endpoint reads across every case at once.
    await pipeline.flush_all_memory(tenant_id=identity.tenant_id)
    summaries = _memory(pipeline).sessions(
        tenant_id=identity.tenant_id, owner_subject=identity.subject
    )
    return {
        "cases": [
            {
                "case_id": s.case_id,
                "title": s.title,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in summaries
        ]
    }


@router.get("/current/memory")
async def view_memory(
    case_id: CaseIdParam = None,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    mem = _memory(pipeline)
    session_id = case_id or identity.session_id
    _require_session_access(mem, identity, session_id)
    # P2: a background distill may still be in flight — flush first, so the chips re-fetch
    # right after /chat already sees the fresh case-state (and the history shows the turn).
    await pipeline.flush_memory(tenant_id=identity.tenant_id, session_id=session_id)
    cs = mem.case_state(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    hist = mem.history(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
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
    case_id: CaseIdParam = None,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    provenance = body.origin if body.origin in _EDIT_ORIGINS else "user-edited"
    mem = _memory(pipeline)
    session_id = case_id or identity.session_id
    _require_session_access(mem, identity, session_id)
    # P2 flush-then-mutate: a pending distill must land BEFORE the user's write, never after
    # it (the user edit is the stronger, later provenance — it must win).
    await pipeline.flush_memory(tenant_id=identity.tenant_id, session_id=session_id)
    mem.edit_fact(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        feld=feld,
        wert=body.wert,
        provenance=provenance,
        owner_subject=identity.subject,
    )
    # M8: a settled input change → recompute + replace the derived slice (no stale kernel value)
    pipeline.recompute_derived_for(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    pipeline.refresh_adaptive_interview(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    return {"status": "ok"}


class FactBatchItem(BaseModel):
    feld: str
    wert: str
    label: str | None = (
        None  # display label from the form schema — echoed verbatim, never decisive
    )


class FactBatch(BaseModel):
    items: list[FactBatchItem]


@router.post("/current/facts")
async def submit_facts(
    body: FactBatch,
    case_id: CaseIdParam = None,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    """The parameter-form batch settle (Phase 2b): write every submitted fact (origin=user-form,
    HARDCODED — the form is the only caller; provenance is never read from the body, so it can't be
    spoofed), then ONE recompute over the merged inputs, then the deterministic confirmation. The
    confirmation echoes the POST-BIND value (a residual mis-parse stays visible) and surfaces a
    clarify-triggering value as a Rückfrage, never as 'übernommen'. Compute must be enabled (503)."""
    mem = _memory(pipeline)
    if pipeline.engine is None:
        raise HTTPException(status_code=503, detail="compute not enabled")
    session_id = case_id or identity.session_id
    _require_session_access(mem, identity, session_id)
    # P2 flush-then-mutate: a pending distill lands before the form writes (mirror edit_fact)
    await pipeline.flush_memory(tenant_id=identity.tenant_id, session_id=session_id)
    for it in body.items:
        mem.edit_fact(
            tenant_id=identity.tenant_id,
            session_id=session_id,
            feld=it.feld,
            wert=it.wert,
            provenance="user-form",
            owner_subject=identity.subject,
        )
    # one recompute over the merged settled inputs (persists the derived slice), then confirm
    comp = pipeline.compute_for(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    pipeline.refresh_adaptive_interview(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    settled = mem.case_state(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    return build_param_confirmation(
        [it.model_dump() for it in body.items], settled, comp
    )


@router.post("/current/preview")
async def preview_facts(
    body: FactBatch,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    """R2 live preview (Modell R2): run the SAME deterministic kern as the committed path over the
    form's DRAFT values and return the Berechnete Werte — but WRITE NOTHING. Read-only: no
    ``edit_fact``, no ``compute_for``/``set_derived``, no ``flush_memory``, no distill, no provenance
    stamp. Because it reuses ``recompute_derived`` (the exact pure function ``compute_for`` calls,
    minus the persist), the preview is byte-identical to the post-``Übernehmen`` recompute for the
    same inputs (Vorschau == Commit). ``user-form`` provenance is set only so the binder treats the
    draft like a form fact; it is never persisted. Compute must be enabled (503)."""
    if pipeline.engine is None:
        raise HTTPException(status_code=503, detail="compute not enabled")
    facts = tuple(
        RememberedFact(feld=it.feld, wert=it.wert, provenance="user-form")
        for it in body.items
    )
    return compute_response(recompute_derived(facts, pipeline.engine))


@router.delete("/current/facts/{feld}")
async def forget_fact(
    feld: str,
    case_id: CaseIdParam = None,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    mem = _memory(pipeline)
    session_id = case_id or identity.session_id
    _require_session_access(mem, identity, session_id)
    # P2 flush-then-mutate: the pending distill lands first, then the forget — a late distill
    # must never re-create what the user just deleted.
    await pipeline.flush_memory(tenant_id=identity.tenant_id, session_id=session_id)
    mem.delete_fact(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        feld=feld,
        owner_subject=identity.subject,
    )
    # M8: forgetting a parent input → recompute → its derived child is evicted (no stale value)
    pipeline.recompute_derived_for(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    pipeline.refresh_adaptive_interview(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    return {"status": "ok"}


@router.delete("/current")
async def forget_all(
    case_id: CaseIdParam = None,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    mem = _memory(pipeline)
    session_id = case_id or identity.session_id
    _require_session_access(mem, identity, session_id)
    # P2 flush-then-mutate: "alles vergessen" is final — flush the pending distill, THEN clear.
    await pipeline.flush_memory(tenant_id=identity.tenant_id, session_id=session_id)
    mem.clear(
        tenant_id=identity.tenant_id,
        session_id=session_id,
        owner_subject=identity.subject,
    )
    pipeline.clear_adaptive_interview(
        tenant_id=identity.tenant_id, session_id=session_id
    )
    return {"status": "ok"}
