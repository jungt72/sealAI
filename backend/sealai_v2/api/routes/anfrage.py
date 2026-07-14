"""POST /api/v2/anfrage — the lead-generation action (owner business model). The user picks a partner
from the Modus-F pool and triggers a structured RFQ: the backend re-renders the M4b briefing from the
SESSION case-state (server-authoritative, tamper-proof — the client cannot inject briefing text),
captures it as a durable lead routed to the partner's ``lead_email``, and returns the briefing preview
so the user transparently sees what is sent.

The final clarification + offer happen between the manufacturer and the user OUTSIDE sealingAI; this
endpoint only hands the worked-out situation to a PAYING (``aktiv``) partner. ``lead_email`` is an
internal routing field — it is NEVER returned to the user. Selection neutrality lives upstream
(``rank_partners``, §3.9): payment gates pool membership, capability fit ranks the pool — a lead can
only be sent to a partner that pool already surfaced.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    flags_from_settings,
    get_capability_store,
    get_lead_store,
    get_partner_registry,
    get_pipeline,
    get_settings,
    require_provider_admission,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import SessionContext, VerifiedIdentity
from sealai_v2.db.leads import Lead, LeadStore
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.render.renderer import ArtifactRenderer, snapshot_from_result
from sealai_v2.security.tenant import TenantContext

router = APIRouter(prefix="/api/v2", tags=["anfrage"])
_renderer = ArtifactRenderer()


class AnfrageRequest(BaseModel):
    partner_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")
    message: str = Field(min_length=1, max_length=8000)


@router.post("/anfrage")
async def anfrage(
    req: AnfrageRequest,
    identity: VerifiedIdentity = Depends(require_provider_admission, scope="request"),
    pipeline: Pipeline = Depends(get_pipeline),
    leads: LeadStore = Depends(get_lead_store),
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
                "message": (
                    "Die Herstellerübergabe ist bis zum unabhängigen "
                    "Fähigkeits- und Interessenkonflikt-Nachweis deaktiviert."
                ),
            },
        )
    # Technical fit and commercial routing are independent gates. The pipeline
    # pool is capability-only; the commercial record supplies only contact and
    # billing-independent routing metadata.
    technical_registry = pipeline.partner_registry
    technical_partner = (
        technical_registry.get(req.partner_id)
        if technical_registry is not None
        else None
    )
    capability = capabilities.get(req.partner_id)
    commercial = commercial_registry.get(req.partner_id)
    if (
        technical_partner is None
        or capability is None
        or not capability.is_verified()
        or commercial is None
        or not commercial.aktiv
        or not commercial.lead_email
    ):
        raise HTTPException(status_code=404, detail="partner nicht verfügbar")

    # Re-render the briefing from the SESSION case-state (P0: tenant/session from the verified token
    # only). Server-authoritative — the briefing reflects the worked-out situation, not client input.
    result = await pipeline.run(
        req.message,
        tenant=TenantContext(identity.tenant_id),
        session=SessionContext(session_id=identity.session_id),
        flags=flags_from_settings(settings),
    )
    art = _renderer.briefing(snapshot_from_result(req.message, result))

    lead_id = leads.store(
        Lead(
            partner_id=technical_partner.hersteller,
            firmenname=technical_partner.firmenname,
            lead_email=commercial.lead_email,  # internal routing — NEVER returned to the user
            tenant_id=identity.tenant_id,
            session_id=identity.session_id,
            briefing_title=art.title,
            briefing_body=art.body,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )

    return {
        "status": "captured",
        "lead_id": lead_id,
        "partner": {
            "hersteller": technical_partner.hersteller,
            "firmenname": technical_partner.firmenname,
        },
        "briefing": {
            "title": art.title,
            "body": art.body,
            "provenance": list(art.provenance),
            "wissensstand": art.wissensstand,
            "risk_flags": list(art.risk_flags),
        },
        "hinweis": (
            "Ihre Anfrage mit dem technischen Briefing wurde an den Hersteller übermittelt. "
            "Der Hersteller kann direkt mit Ihnen in Kontakt treten; die finale Klärung und "
            "Angebotserstellung erfolgen zwischen Ihnen und dem Hersteller außerhalb von sealingAI."
        ),
    }
