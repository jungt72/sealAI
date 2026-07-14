"""Wissens-Beitrag surface (owner business: users improve sealingAI by sharing real cases + outcomes).
- POST /api/v2/contribute — a USER opts to share their situation + outcome (anonymous by default). Captured
  as an untrusted DRAFT in the review queue; identity is dropped when anonymous. P0: tenant/subject from the
  verified token only, used solely for non-anonymous provenance.
- GET/PUT /api/v2/admin/contributions — the OWNER review queue (require_platform_owner). The owner reviews, then
  promotes a case to a field_validated Fachkarte / eval-trap OUTSIDE this endpoint (the review gate).
STRUCTURAL FIREWALL: a contribution NEVER feeds the trust spine / grounding / produktspec — it is a separate
store, reachable only by the user (write) and the owner (review)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    current_identity,
    get_contribution_store,
    require_platform_owner,
)
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.contributions import Contribution, ContributionStore

router = APIRouter(prefix="/api/v2", tags=["contribute"])

_VALID_STATUS = ("neu", "reviewed", "promoted", "rejected")


class CaseFact(BaseModel):
    feld: str = Field(default="", max_length=255)
    wert: str = Field(default="", max_length=2000)


class ContributeRequest(BaseModel):
    anonym: bool = True
    situation: str = Field(default="", max_length=4000)
    recommendation: str = Field(default="", max_length=4000)
    outcome: str = Field(default="", max_length=4000)
    case_state: list[CaseFact] = Field(default_factory=list)


@router.post("/contribute")
def contribute(
    req: ContributeRequest,
    identity: VerifiedIdentity = Depends(current_identity),
    store: ContributionStore = Depends(get_contribution_store),
) -> dict:
    # Anonymous → no identity captured (tenant_ref='anon', no subject). The structured case-state is
    # technical (physics, not PII); the situation/outcome free-text is scrubbed by the owner at review.
    contribution_id = store.store(
        Contribution(
            anonym=req.anonym,
            tenant_ref="anon" if req.anonym else identity.tenant_id,
            subject_ref="" if req.anonym else identity.subject,
            situation=req.situation,
            case_state_json=[{"feld": f.feld, "wert": f.wert} for f in req.case_state],
            recommendation=req.recommendation,
            outcome=req.outcome,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    return {
        "status": "captured",
        "id": contribution_id,
        "anonym": req.anonym,
        "hinweis": (
            "Danke — dein Beitrag geht (ungeprüft) in die Wissens-Review-Queue. Er verbessert sealingAI "
            "erst nach fachlicher Prüfung und fließt nie automatisch in eine Empfehlung ein."
        ),
    }


@router.get("/admin/contributions")
def list_contributions(
    _: VerifiedIdentity = Depends(require_platform_owner),
    store: ContributionStore = Depends(get_contribution_store),
) -> dict:
    return {
        "contributions": [
            {
                "id": c.id,
                "anonym": c.anonym,
                "tenant_ref": c.tenant_ref,
                "subject_ref": c.subject_ref,
                "situation": c.situation,
                "case_state": c.case_state_json,
                "recommendation": c.recommendation,
                "outcome": c.outcome,
                "created_at": c.created_at,
                "status": c.status,
                "review_note": c.review_note,
            }
            for c in store.list_all()
        ]
    }


class StatusUpdate(BaseModel):
    status: str
    review_note: str = Field(default="", max_length=4000)


@router.put("/admin/contributions/{contribution_id}/status")
def set_contribution_status(
    contribution_id: int,
    body: StatusUpdate,
    _: VerifiedIdentity = Depends(require_platform_owner),
    store: ContributionStore = Depends(get_contribution_store),
) -> dict:
    if body.status not in _VALID_STATUS:
        raise HTTPException(
            status_code=422, detail=f"status must be one of {_VALID_STATUS}"
        )
    if not store.set_status(contribution_id, body.status, body.review_note):
        raise HTTPException(status_code=404, detail="contribution nicht gefunden")
    return {"id": contribution_id, "status": body.status}
