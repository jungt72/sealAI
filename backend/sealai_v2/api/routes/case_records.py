"""Durable case snapshots and human-reviewed decision records."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    get_case_decision_store,
    get_settings,
    require_decision_reviewer,
    require_legal_acceptance,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.decision_records import CaseDecisionError

router = APIRouter(prefix="/api/v2/cases", tags=["case-records"])


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    risk_class: Literal["A", "B", "C", "D", "E"] = "C"


class SnapshotCreate(BaseModel):
    state: dict = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)


class DecisionCreate(BaseModel):
    snapshot_id: str = Field(min_length=1, max_length=64)
    decision_type: str = Field(min_length=1, max_length=64)
    conclusion: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    uncertainty: Literal[
        "bounded", "conditional", "conflicted", "not_sufficiently_supported"
    ]
    responsibilities: dict = Field(min_length=1)
    approvals_required: list[str] = Field(
        default_factory=lambda: ["technical_review"], min_length=1
    )
    supersedes_decision_id: str = Field(default="", max_length=64)


class ApprovalCreate(BaseModel):
    status: Literal["approved", "rejected", "conditional"]
    scope: str = "technical review of recorded evidence and snapshot"
    note: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_case_records(settings: Settings) -> None:
    if not settings.case_decision_records_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "product_mode_unavailable",
                "mode": "case_decision_records",
                "maturity": "in_build_not_activated",
            },
        )


@router.post("")
def create_case(
    body: CaseCreate,
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    store=Depends(get_case_decision_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_case_records(settings)
    try:
        record = store.create_case(
            tenant_id=identity.tenant_id,
            title=body.title,
            risk_class=body.risk_class,
            owner_subject=identity.subject,
            now=_now(),
        )
    except CaseDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"case": asdict(record)}


@router.get("/{case_id}")
def get_case(
    case_id: str,
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    store=Depends(get_case_decision_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_case_records(settings)
    try:
        bundle = store.case_bundle(tenant_id=identity.tenant_id, case_id=case_id)
    except CaseDecisionError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return {
        "case": asdict(bundle["case"]),
        "snapshots": [asdict(item) for item in bundle["snapshots"]],
        "decisions": [asdict(item) for item in bundle["decisions"]],
        "approvals": [asdict(item) for item in bundle["approvals"]],
        "release_boundary": (
            "Eine sealingAI-Review ist keine Bauteil-, Hersteller- oder Einsatzfreigabe."
        ),
    }


@router.post("/{case_id}/snapshots")
def create_snapshot(
    case_id: str,
    body: SnapshotCreate,
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    store=Depends(get_case_decision_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_case_records(settings)
    try:
        snapshot = store.create_snapshot(
            tenant_id=identity.tenant_id,
            case_id=case_id,
            state=body.state,
            evidence_refs=tuple(body.evidence_refs),
            open_points=tuple(body.open_points),
            actor=identity.subject,
            now=_now(),
        )
    except CaseDecisionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"snapshot": asdict(snapshot)}


@router.post("/{case_id}/decisions")
def create_decision(
    case_id: str,
    body: DecisionCreate,
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    store=Depends(get_case_decision_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_case_records(settings)
    try:
        decision = store.create_decision(
            tenant_id=identity.tenant_id,
            case_id=case_id,
            snapshot_id=body.snapshot_id,
            decision_type=body.decision_type,
            conclusion=body.conclusion,
            rationale=body.rationale,
            evidence_refs=tuple(body.evidence_refs),
            uncertainty=body.uncertainty,
            responsibilities=body.responsibilities,
            approvals_required=tuple(body.approvals_required),
            actor=identity.subject,
            now=_now(),
            supersedes_decision_id=body.supersedes_decision_id,
        )
    except CaseDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "decision": asdict(decision),
        "release_authority": "external_manufacturer_or_responsible_engineer",
    }


@router.post("/decisions/{decision_id}/approvals")
def add_approval(
    decision_id: str,
    body: ApprovalCreate,
    identity: VerifiedIdentity = Depends(require_decision_reviewer),
    store=Depends(get_case_decision_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_case_records(settings)
    try:
        approval = store.add_approval(
            tenant_id=identity.tenant_id,
            decision_id=decision_id,
            status=body.status,
            actor_subject=identity.subject,
            actor_role="decision_reviewer",
            scope=body.scope,
            note=body.note,
            now=_now(),
        )
    except CaseDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "approval": asdict(approval),
        "release_authority": "external_manufacturer_or_responsible_engineer",
    }
