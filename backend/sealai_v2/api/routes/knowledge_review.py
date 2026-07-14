"""Independent adjudication surface for the authoritative knowledge ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from sealai_v2.api.deps import (
    current_identity,
    get_knowledge_ledger,
    get_settings,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    KnowledgeClaimNotFound,
    KnowledgeLedgerError,
)

router = APIRouter(prefix="/api/v2/admin/knowledge", tags=["knowledge-review"])


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_status: Literal["reviewed", "approved", "quarantined", "rejected"]
    independent_review_attested: bool = False
    note: str = Field(default="", max_length=4000)
    evidence: list[dict] = Field(default_factory=list, max_length=100)
    applicability: dict = Field(default_factory=dict)
    uncertainty: (
        Literal["bounded", "conditional", "conflicted", "not_sufficiently_supported"]
        | None
    ) = None
    transferability: (
        Literal[
            "source_specific",
            "family_level_orientation",
            "application_dependent",
            "not_assessed",
        ]
        | None
    ) = None
    review_expires_at: str = ""
    conflicts: list[str] = Field(default_factory=list, max_length=100)
    change_reason: str = Field(default="", max_length=4000)


def _require_review_surface(settings: Settings) -> None:
    if not settings.knowledge_review_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "product_mode_unavailable",
                "mode": "knowledge_review",
                "maturity": "review_plane_not_activated",
            },
        )


def _require_review_role(
    identity: VerifiedIdentity, settings: Settings, *, approval: bool = False
) -> None:
    required = (
        settings.auth_knowledge_approver_role
        if approval
        else settings.auth_knowledge_reviewer_role
    )
    if required not in identity.roles:
        detail = (
            "knowledge approver role required"
            if approval
            else "knowledge reviewer role required"
        )
        raise HTTPException(status_code=403, detail=detail)
    incompatible = {
        settings.auth_tenant_admin_role,
        settings.auth_platform_owner_role,
        settings.auth_system_operator_role,
        settings.auth_knowledge_contributor_role,
        (
            settings.auth_knowledge_reviewer_role
            if approval
            else settings.auth_knowledge_approver_role
        ),
    }
    if not incompatible.isdisjoint(identity.roles):
        raise HTTPException(
            status_code=403,
            detail="knowledge governance roles must be held by separate identities",
        )


def _require_review_reader(identity: VerifiedIdentity, settings: Settings) -> None:
    allowed = {
        settings.auth_knowledge_reviewer_role,
        settings.auth_knowledge_approver_role,
    }
    if allowed.isdisjoint(identity.roles):
        raise HTTPException(status_code=403, detail="knowledge review role required")


@router.get("/claims")
def list_claims(
    status: Literal["draft", "reviewed", "approved", "quarantined", "rejected"] = (
        Query(default="quarantined")
    ),
    limit: int = Query(default=100, ge=1, le=500),
    identity: VerifiedIdentity = Depends(current_identity),
    ledger=Depends(get_knowledge_ledger),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_review_surface(settings)
    _require_review_reader(identity, settings)
    try:
        claims = ledger.list_claims(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            statuses=(status,),
            limit=limit,
        )
    except KnowledgeLedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"claims": list(claims), "status": status, "authoritative": True}


@router.post("/claims/{claim_id}/review")
def review_claim(
    claim_id: str,
    body: ClaimReview,
    identity: VerifiedIdentity = Depends(current_identity),
    ledger=Depends(get_knowledge_ledger),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_review_surface(settings)
    _require_review_role(identity, settings, approval=body.to_status == "approved")
    if body.to_status == "approved" and not body.independent_review_attested:
        raise HTTPException(
            status_code=400,
            detail="approval requires an independent human review attestation",
        )
    note = body.note.strip()
    if body.independent_review_attested:
        note = f"{note}\nIndependent human review attested.".strip()
    try:
        claim = ledger.review_claim(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            claim_id=claim_id,
            to_status=body.to_status,
            actor=identity.subject,
            now=datetime.now(timezone.utc).isoformat(),
            note=note,
            evidence=tuple(body.evidence),
            applicability=body.applicability,
            uncertainty=body.uncertainty,
            transferability=body.transferability,
            review_expires_at=body.review_expires_at or None,
            conflicts=tuple(body.conflicts),
            change_reason=body.change_reason,
        )
    except KnowledgeClaimNotFound as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc
    except KnowledgeLedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"claim": claim, "knowledge_mode_activated": False}
