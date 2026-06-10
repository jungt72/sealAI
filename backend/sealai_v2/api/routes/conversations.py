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
def view_memory(
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    mem = _memory(pipeline)
    cs = mem.case_state(tenant_id=identity.tenant_id, session_id=identity.session_id)
    hist = mem.history(tenant_id=identity.tenant_id, session_id=identity.session_id)
    return {
        "case_state": [
            {"feld": f.feld, "wert": f.wert, "provenance": f.provenance} for f in cs
        ],
        "history": [{"role": t.role, "text": t.text} for t in hist],
    }


class FactEdit(BaseModel):
    wert: str


@router.put("/current/facts/{feld}")
def edit_fact(
    feld: str,
    body: FactEdit,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    _memory(pipeline).edit_fact(
        tenant_id=identity.tenant_id,
        session_id=identity.session_id,
        feld=feld,
        wert=body.wert,
    )
    return {"status": "ok"}


@router.delete("/current/facts/{feld}")
def forget_fact(
    feld: str,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    _memory(pipeline).delete_fact(
        tenant_id=identity.tenant_id, session_id=identity.session_id, feld=feld
    )
    return {"status": "ok"}


@router.delete("/current")
def forget_all(
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    _memory(pipeline).clear(
        tenant_id=identity.tenant_id, session_id=identity.session_id
    )
    return {"status": "ok"}
