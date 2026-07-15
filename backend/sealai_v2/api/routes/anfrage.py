"""Governed, idempotent RFQ capture plus owner-authorized cancellation quarantine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from sealai_v2.api.case_artifacts import project_briefing
from sealai_v2.api.deps import (
    current_identity,
    get_capability_store,
    get_lead_store,
    get_lifecycle_control_store,
    get_partner_registry,
    get_pipeline,
    get_settings,
    require_legal_acceptance,
)
from sealai_v2.api.lifecycle_schemas import (
    HandoffGovernance,
    LifecycleReason,
    canonical_content_bytes,
    has_prompt_injection_signal,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.engine import bind_database_case
from sealai_v2.db.leads import Lead, LeadStore
from sealai_v2.db.contributions import (
    LifecycleTransitionConflict,
    LifecycleTransitionUnavailable,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.render.renderer import ArtifactRenderer
from sealai_v2.security.lifecycle_control import (
    LifecycleControlStore,
    LifecyclePolicy,
    canonical_request_digest,
)

router = APIRouter(prefix="/api/v2", tags=["anfrage"])
_renderer = ArtifactRenderer()


class AnfrageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")
    case_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._~-]+$")
    case_revision: int = Field(ge=0)
    governance: HandoffGovernance


class LeadCancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: Literal["lead_cancelled"] = "lead_cancelled"


def _validate_policy(
    governance: HandoffGovernance, identity: VerifiedIdentity, settings: Settings
) -> None:
    if governance.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=403, detail="tenant scope mismatch")
    if (
        governance.policy_authority_ref,
        governance.purpose_version,
        governance.consent_version,
    ) != (
        settings.api_lifecycle_policy_authority_ref,
        settings.api_lifecycle_purpose_version,
        settings.api_lifecycle_consent_version,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "governance_version_mismatch",
                "message": "Die Governance-Version ist nicht aktuell.",
            },
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


def _retention_review_after(settings: Settings, now: datetime) -> str | None:
    if settings.api_lifecycle_retention_days is None:
        return None
    return (
        (now + timedelta(days=settings.api_lifecycle_retention_days))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _lead_response(lead: Lead, *, replay: bool) -> dict:
    available = lead.lifecycle_state == "active"
    return {
        "status": "captured" if available else "review_quarantined",
        "lead_id": lead.id,
        "partner": {
            "hersteller": lead.partner_id,
            "firmenname": lead.firmenname,
        },
        "briefing": {
            "title": lead.briefing_title,
            "body": lead.briefing_body,
            "provenance": list(lead.briefing_provenance),
            "wissensstand": lead.briefing_wissensstand,
            "risk_flags": list(lead.briefing_risk_flags),
        },
        "case_id": lead.case_id,
        "case_revision": lead.case_revision,
        "read_only": True,
        "lifecycle_state": lead.lifecycle_state,
        "prompt_trust": "untrusted",
        "idempotent_replay": replay,
        "hinweis": (
            "Die Anfrage ist für den geschützten Herstellerzugriff erfasst. "
            "Weitere Klärung und Angebotserstellung erfolgen außerhalb von sealingAI."
            if available
            else "Die Anfrage ist in der Review-Quarantäne und wurde dem Hersteller nicht bereitgestellt."
        ),
    }


@router.post("/anfrage")
async def anfrage(
    request: AnfrageRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    pipeline: Pipeline = Depends(get_pipeline),
    leads: LeadStore = Depends(get_lead_store),
    control: LifecycleControlStore = Depends(get_lifecycle_control_store),
    capabilities=Depends(get_capability_store),
    commercial_registry=Depends(get_partner_registry),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.manufacturer_handoff_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "product_mode_unavailable",
                "mode": "manufacturer_handoff",
                "maturity": "capability_review_required",
                "message": "Die Herstellerübergabe ist noch nicht aktiviert.",
            },
        )
    if not settings.api_lifecycle_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "api_lifecycle_unavailable",
                "message": "Der kontrollierte Anfrageweg ist noch nicht aktiviert.",
            },
        )
    _validate_policy(request.governance, identity, settings)

    technical_registry = pipeline.partner_registry
    technical_partner = (
        technical_registry.get(request.partner_id)
        if technical_registry is not None
        else None
    )
    capability = capabilities.get(request.partner_id)
    commercial = commercial_registry.get(request.partner_id)
    if (
        technical_partner is None
        or capability is None
        or not capability.is_verified()
        or commercial is None
        or not commercial.aktiv
        or not commercial.lead_email
    ):
        raise HTTPException(status_code=404, detail="partner nicht verfügbar")

    payload = request.model_dump(mode="json")
    try:
        decision = await run_in_threadpool(
            control.admit,
            identity,
            LifecyclePolicy.from_settings(settings),
            action="lead.create",
            idempotency_key=idempotency_key,
            request_digest=canonical_request_digest(payload),
            # Reserve the complete case ceiling before any projection work. The conservative,
            # non-refundable reservation can overcount but can never undercount stored content.
            estimated_bytes=settings.api_max_case_payload_bytes,
        )
    except Exception:
        raise HTTPException(
            status_code=503, detail="API lifecycle control unavailable"
        ) from None
    _decision_or_error(decision)
    assert decision.admission is not None
    admission = decision.admission
    if admission.replay:
        prior = await run_in_threadpool(
            leads.get_owned, int(admission.resource_id or "0"), identity
        )
        if prior is None:
            raise HTTPException(
                status_code=503, detail="idempotent lead state unavailable"
            )
        return _lead_response(prior, replay=True)

    try:
        with bind_database_case(request.case_id):
            snapshot, artifact = await project_briefing(
                pipeline=pipeline,
                identity=identity,
                case_id=request.case_id,
                case_revision=request.case_revision,
                renderer=_renderer,
            )
        content_payload = {
            "title": artifact.title,
            "body": artifact.body,
            "provenance": list(artifact.provenance),
            "wissensstand": artifact.wissensstand,
            "risk_flags": list(artifact.risk_flags),
        }
        content_bytes = canonical_content_bytes(content_payload)
        if content_bytes > settings.api_max_case_payload_bytes:
            raise HTTPException(
                status_code=413, detail="lead case payload exceeds the hard limit"
            )
        injection_signal = has_prompt_injection_signal(
            artifact.title, artifact.body, *artifact.provenance
        )
        lifecycle_state = (
            "active"
            if request.governance.pii_classification.value == "none_declared"
            and not injection_signal
            else "review_quarantined"
        )
        now = datetime.now(timezone.utc)
        lead_id = await run_in_threadpool(
            leads.store,
            Lead(
                admission_request_id=admission.request_id,
                partner_id=technical_partner.hersteller,
                firmenname=technical_partner.firmenname,
                lead_email=commercial.lead_email,
                tenant_id=identity.tenant_id,
                session_id=snapshot.case_id,
                owner_subject=identity.subject,
                case_id=snapshot.case_id,
                case_revision=snapshot.case_revision,
                briefing_title=artifact.title,
                briefing_body=artifact.body,
                briefing_provenance=tuple(artifact.provenance),
                briefing_wissensstand=artifact.wissensstand,
                briefing_risk_flags=tuple(artifact.risk_flags),
                policy_authority_ref=request.governance.policy_authority_ref,
                purpose_version=request.governance.purpose_version,
                consent_version=request.governance.consent_version,
                handoff_confirmed=True,
                pii_classification=request.governance.pii_classification.value,
                prompt_trust="untrusted",
                prompt_injection_signal=injection_signal,
                lifecycle_state=lifecycle_state,
                content_bytes=content_bytes,
                retention_review_after=_retention_review_after(settings, now),
                created_at=now.isoformat(),
            ),
        )
        await run_in_threadpool(
            control.complete,
            admission.request_id,
            completion_token=admission.completion_token,
            outcome="success",
            resource_type="lead",
            resource_id=str(lead_id),
        )
    except Exception:
        try:
            await run_in_threadpool(
                control.complete,
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        except Exception:
            pass
        raise
    stored = await run_in_threadpool(leads.get_owned, lead_id, identity)
    if stored is None:
        raise HTTPException(status_code=503, detail="captured lead state unavailable")
    return _lead_response(stored, replay=False)


@router.post("/leads/{lead_id}/cancel")
async def cancel_lead(
    lead_id: int,
    body: LeadCancellationRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
    identity: VerifiedIdentity = Depends(current_identity),
    settings: Settings = Depends(get_settings),
    leads: LeadStore = Depends(get_lead_store),
    control: LifecycleControlStore = Depends(get_lifecycle_control_store),
) -> dict:
    if not settings.api_lifecycle_enabled:
        raise HTTPException(status_code=503, detail="API lifecycle is disabled")
    payload = {"lead_id": lead_id, **body.model_dump()}
    try:
        decision = await run_in_threadpool(
            control.admit,
            identity,
            LifecyclePolicy.from_settings(settings),
            action="lead.cancel",
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
        receipt = await run_in_threadpool(
            leads.cancel_owned,
            lead_id,
            identity,
            idempotency_key=idempotency_key,
            reason_code=LifecycleReason.LEAD_CANCELLED.value,
        )
        if receipt is None:
            raise HTTPException(status_code=404, detail="lead not found")
        if not admission.replay:
            await run_in_threadpool(
                control.complete,
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="success",
                resource_type="receipt",
                resource_id=receipt.receipt_id,
            )
    except LifecycleTransitionConflict:
        if not admission.replay:
            await run_in_threadpool(
                control.complete,
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "lead_cancellation_conflict",
                "message": "Die Anfrage kann in ihrem aktuellen Zustand nicht erneut gesperrt werden.",
            },
        ) from None
    except LifecycleTransitionUnavailable:
        if not admission.replay:
            await run_in_threadpool(
                control.complete,
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        raise HTTPException(
            status_code=503, detail="cancellation receipt unavailable"
        ) from None
    except HTTPException:
        if not admission.replay:
            await run_in_threadpool(
                control.complete,
                admission.request_id,
                completion_token=admission.completion_token,
                outcome="error",
            )
        raise
    return {
        "status": "cancelled_quarantined",
        "receipt_id": receipt.receipt_id,
        "receipt_digest": receipt.receipt_digest,
        "issued_at": receipt.issued_at,
        "policy_authority_ref": receipt.policy_authority_ref,
        "idempotent_replay": admission.replay or receipt.replay,
        "hinweis": "Die Anfrage ist gesperrt und bleibt für die nachvollziehbare Prüfung in Quarantäne.",
    }
