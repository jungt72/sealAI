"""Governed contribution intake, bounded owner queue, and withdrawal receipts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sealai_v2.api.deps import (
    current_identity,
    get_contribution_store,
    get_lifecycle_control_store,
    get_settings,
    require_platform_owner,
)
from sealai_v2.api.lifecycle_schemas import (
    GovernanceEnvelope,
    LifecycleReason,
    canonical_content_bytes,
    has_prompt_injection_signal,
)
from sealai_v2.api.pagination import InvalidCursor, decode_cursor
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.contributions import (
    Contribution,
    ContributionStore,
    LifecycleTransitionConflict,
    LifecycleTransitionUnavailable,
)
from sealai_v2.security.lifecycle_control import (
    LifecycleControlStore,
    LifecyclePolicy,
    canonical_request_digest,
    identity_scope_refs,
)

router = APIRouter(prefix="/api/v2", tags=["contribute"])

_VALID_STATUS = ("pending", "under_review", "reviewed", "rejected")


class CaseFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feld: str = Field(min_length=1, max_length=255)
    wert: str = Field(min_length=1, max_length=2000)


class ContributeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anonym: bool = True
    situation: str = Field(default="", max_length=4000)
    recommendation: str = Field(default="", max_length=4000)
    outcome: str = Field(default="", max_length=4000)
    case_state: list[CaseFact] = Field(default_factory=list, max_length=64)
    governance: GovernanceEnvelope

    @model_validator(mode="after")
    def require_content(self) -> "ContributeRequest":
        if (
            not any(
                value.strip()
                for value in (self.situation, self.recommendation, self.outcome)
            )
            and not self.case_state
        ):
            raise ValueError("contribution content must not be empty")
        return self


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "under_review", "reviewed", "rejected"]
    review_note: str = Field(default="", max_length=4000)


class WithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: Literal["user_withdrawal"] = "user_withdrawal"


def _lifecycle_disabled() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "api_lifecycle_unavailable",
            "message": "Der kontrollierte Beitragsweg ist noch nicht aktiviert.",
        },
    )


def _validate_policy(
    governance: GovernanceEnvelope, identity: VerifiedIdentity, settings: Settings
) -> None:
    if governance.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=403, detail="tenant scope mismatch")
    expected = (
        settings.api_lifecycle_policy_authority_ref,
        settings.api_lifecycle_purpose_version,
        settings.api_lifecycle_consent_version,
    )
    supplied = (
        governance.policy_authority_ref,
        governance.purpose_version,
        governance.consent_version,
    )
    if supplied != expected:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "governance_version_mismatch",
                "message": "Die Governance-Version ist nicht aktuell.",
            },
        )


def _retention_review_after(settings: Settings, now: datetime) -> str | None:
    if settings.api_lifecycle_retention_days is None:
        return None
    return (
        (now + timedelta(days=settings.api_lifecycle_retention_days))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _decision_or_error(decision) -> None:
    if decision.allowed:
        return
    headers = (
        {"Retry-After": str(decision.retry_after_s)}
        if decision.retry_after_s is not None
        else None
    )
    raise HTTPException(
        status_code=decision.status_code,
        detail={"code": decision.reason, "message": "API lifecycle request denied"},
        headers=headers,
    )


def _contribution_response(contribution_id: int, *, anonym: bool, replay: bool) -> dict:
    return {
        "status": "captured",
        "id": contribution_id,
        "anonym": anonym,
        "lifecycle_state": "quarantined",
        "prompt_trust": "untrusted",
        "idempotent_replay": replay,
        "hinweis": (
            "Der Beitrag wurde als untrusted markiert und in die Review-Quarantäne gelegt. "
            "Er wird nicht automatisch für Antworten oder Empfehlungen verwendet."
        ),
    }


@router.get("/contribute/policy")
def contribution_policy(
    identity: VerifiedIdentity = Depends(current_identity),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Version identities only; legal text and retention duration remain external authority."""
    return {
        "enabled": settings.api_lifecycle_enabled,
        "tenant_id": identity.tenant_id,
        "policy_authority_ref": settings.api_lifecycle_policy_authority_ref,
        "purpose_version": settings.api_lifecycle_purpose_version,
        "consent_version": settings.api_lifecycle_consent_version,
        "retention": (
            {
                "mode": "human_authority_configured",
                "days": settings.api_lifecycle_retention_days,
            }
            if settings.api_lifecycle_retention_days is not None
            else {"mode": "human_authority_required", "days": None}
        ),
        "prompt_trust": "untrusted",
        "initial_state": "quarantined",
    }


@router.post("/contribute")
def contribute(
    request: ContributeRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
    identity: VerifiedIdentity = Depends(current_identity),
    settings: Settings = Depends(get_settings),
    control: LifecycleControlStore = Depends(get_lifecycle_control_store),
    store: ContributionStore = Depends(get_contribution_store),
) -> dict:
    if not settings.api_lifecycle_enabled:
        raise _lifecycle_disabled()
    _validate_policy(request.governance, identity, settings)
    if len(request.case_state) > settings.api_max_case_facts:
        raise HTTPException(
            status_code=413, detail="case fact count exceeds the hard limit"
        )
    case_payload = {
        "situation": request.situation,
        "recommendation": request.recommendation,
        "outcome": request.outcome,
        "case_state": [fact.model_dump() for fact in request.case_state],
    }
    case_bytes = canonical_content_bytes(case_payload)
    if case_bytes > settings.api_max_case_payload_bytes:
        raise HTTPException(
            status_code=413, detail="case payload exceeds the hard limit"
        )
    full_payload = request.model_dump(mode="json")
    estimated_bytes = canonical_content_bytes(full_payload)
    try:
        decision = control.admit(
            identity,
            LifecyclePolicy.from_settings(settings),
            action="contribution.create",
            idempotency_key=idempotency_key,
            request_digest=canonical_request_digest(full_payload),
            estimated_bytes=estimated_bytes,
        )
    except Exception:
        raise HTTPException(
            status_code=503, detail="API lifecycle control unavailable"
        ) from None
    _decision_or_error(decision)
    assert decision.admission is not None
    admission = decision.admission
    if admission.replay:
        prior = store.get_owned(int(admission.resource_id or "0"), identity)
        if prior is None:
            raise HTTPException(
                status_code=503, detail="idempotent contribution state unavailable"
            )
        return _contribution_response(prior.id, anonym=prior.anonym, replay=True)

    now = datetime.now(timezone.utc)
    _, actor_ref = identity_scope_refs(identity)
    injection_signal = has_prompt_injection_signal(
        request.situation,
        request.recommendation,
        request.outcome,
        *(fact.wert for fact in request.case_state),
    )
    quarantine_reasons = ["intake_review_required"]
    if request.governance.pii_classification.value != "none_declared":
        quarantine_reasons.append("pii_review_required")
    if injection_signal:
        quarantine_reasons.append("prompt_injection_signal")
    if (
        request.governance.rights_basis.value == "review_required"
        or request.governance.license_id.value == "review_required"
    ):
        quarantine_reasons.append("rights_review_required")

    try:
        contribution_id = store.store(
            Contribution(
                admission_request_id=admission.request_id,
                anonym=request.anonym,
                tenant_ref=identity.tenant_id,
                subject_ref="" if request.anonym else identity.subject,
                owner_subject_ref=actor_ref,
                situation=request.situation,
                case_state_json=[fact.model_dump() for fact in request.case_state],
                recommendation=request.recommendation,
                outcome=request.outcome,
                policy_authority_ref=request.governance.policy_authority_ref,
                purpose_version=request.governance.purpose_version,
                consent_version=request.governance.consent_version,
                rights_basis=request.governance.rights_basis.value,
                license_id=request.governance.license_id.value,
                provenance=request.governance.provenance,
                document_type=request.governance.document_type.value,
                pii_classification=request.governance.pii_classification.value,
                prompt_trust="untrusted",
                prompt_injection_signal=injection_signal,
                content_bytes=estimated_bytes,
                created_at=now.isoformat(),
                retention_review_after=_retention_review_after(settings, now),
                quarantine_reason=",".join(quarantine_reasons),
            )
        )
        control.complete(
            admission.request_id,
            completion_token=admission.completion_token,
            outcome="success",
            resource_type="contribution",
            resource_id=str(contribution_id),
        )
    except Exception:
        try:
            control.complete(
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        except Exception:
            pass
        raise
    return _contribution_response(contribution_id, anonym=request.anonym, replay=False)


@router.post("/contributions/{contribution_id}/withdrawal")
def withdraw_contribution(
    contribution_id: int,
    body: WithdrawalRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
    identity: VerifiedIdentity = Depends(current_identity),
    settings: Settings = Depends(get_settings),
    control: LifecycleControlStore = Depends(get_lifecycle_control_store),
    store: ContributionStore = Depends(get_contribution_store),
) -> dict:
    if not settings.api_lifecycle_enabled:
        raise _lifecycle_disabled()
    payload = {"contribution_id": contribution_id, **body.model_dump()}
    try:
        decision = control.admit(
            identity,
            LifecyclePolicy.from_settings(settings),
            action="contribution.withdraw",
            idempotency_key=idempotency_key,
            request_digest=canonical_request_digest(payload),
            estimated_bytes=0,
        )
    except Exception:
        raise HTTPException(
            status_code=503, detail="API lifecycle control unavailable"
        ) from None
    _decision_or_error(decision)
    assert decision.admission is not None
    admission = decision.admission
    try:
        receipt = store.withdraw(
            contribution_id,
            identity,
            idempotency_key=idempotency_key,
            reason_code=LifecycleReason.USER_WITHDRAWAL.value,
        )
        if receipt is None:
            raise HTTPException(status_code=404, detail="contribution not found")
        if not admission.replay:
            control.complete(
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="success",
                resource_type="receipt",
                resource_id=receipt.receipt_id,
            )
    except LifecycleTransitionConflict:
        if not admission.replay:
            control.complete(
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "contribution_withdrawal_conflict",
                "message": "Der Beitrag kann in seinem aktuellen Zustand nicht erneut gesperrt werden.",
            },
        ) from None
    except LifecycleTransitionUnavailable:
        if not admission.replay:
            control.complete(
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        raise HTTPException(
            status_code=503, detail="withdrawal receipt unavailable"
        ) from None
    except HTTPException:
        if not admission.replay:
            control.complete(
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        raise
    return {
        "status": "withdrawn_quarantined",
        "receipt_id": receipt.receipt_id,
        "receipt_digest": receipt.receipt_digest,
        "issued_at": receipt.issued_at,
        "policy_authority_ref": receipt.policy_authority_ref,
        "idempotent_replay": admission.replay or receipt.replay,
        "hinweis": "Der Beitrag ist gesperrt und bleibt für die nachvollziehbare Prüfung in Quarantäne.",
    }


@router.get("/admin/contributions")
def list_contributions(
    _: VerifiedIdentity = Depends(require_platform_owner),
    store: ContributionStore = Depends(get_contribution_store),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
) -> dict:
    try:
        before_id = decode_cursor(cursor)
    except InvalidCursor:
        raise HTTPException(status_code=400, detail="invalid cursor") from None
    page = store.page(before_id=before_id, limit=limit)
    return {
        "contributions": [
            {
                "id": contribution.id,
                "anonym": contribution.anonym,
                "tenant_ref": contribution.tenant_ref,
                "subject_ref": contribution.subject_ref,
                "situation": contribution.situation,
                "case_state": contribution.case_state_json,
                "recommendation": contribution.recommendation,
                "outcome": contribution.outcome,
                "created_at": contribution.created_at,
                "status": contribution.status,
                "review_note": contribution.review_note,
                "lifecycle_state": contribution.lifecycle_state,
                "document_type": contribution.document_type,
                "pii_classification": contribution.pii_classification,
                "prompt_trust": contribution.prompt_trust,
                "prompt_injection_signal": contribution.prompt_injection_signal,
                "quarantine_reason": contribution.quarantine_reason,
            }
            for contribution in page.items
        ],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


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
        raise HTTPException(status_code=404, detail="contribution not found")
    return {
        "id": contribution_id,
        "status": body.status,
        "lifecycle_state": "review_quarantined",
    }
