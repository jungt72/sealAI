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
    current_identity,
    flags_from_settings,
    get_lead_store,
    get_pipeline,
    get_settings,
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
    partner_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


@router.post("/anfrage")
async def anfrage(
    req: AnfrageRequest,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
    leads: LeadStore = Depends(get_lead_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    # A lead can only be routed to a PAYING (aktiv) partner the pool actually lists; an unknown or
    # inactive id (or an unconfigured pool) yields a neutral 404 that leaks no internal state.
    registry = pipeline.partner_registry
    partner = registry.get(req.partner_id) if registry is not None else None
    if partner is None or not partner.aktiv:
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
            partner_id=partner.hersteller,
            firmenname=partner.firmenname,
            lead_email=partner.lead_email,  # internal routing — NEVER returned to the user
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
        "partner": {"hersteller": partner.hersteller, "firmenname": partner.firmenname},
        "briefing": {
            "title": art.title,
            "body": art.body,
            "provenance": list(art.provenance),
        },
        "hinweis": (
            "Ihre Anfrage mit dem technischen Briefing wurde an den Hersteller übermittelt. "
            "Der Hersteller kann direkt mit Ihnen in Kontakt treten; die finale Klärung und "
            "Angebotserstellung erfolgen zwischen Ihnen und dem Hersteller außerhalb von sealingAI."
        ),
    }
