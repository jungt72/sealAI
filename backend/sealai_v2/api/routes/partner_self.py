"""Manufacturer SELF-SERVICE surface (/api/v2/partner/me) — a paying partner manages their OWN profile
and reads their OWN leads. Gated by ``require_manufacturer`` (the manufacturer realm-role + a
hersteller_id claim); EVERYTHING is scoped to ``identity.hersteller_id``, so a manufacturer can only
ever touch their own record — there is no id parameter to abuse.

The owner-controlled fields (``aktiv``, ``plan``, ``partner_seit``) are NOT editable here — they are
the paid-membership controls (owner hoheit). A manufacturer can never self-activate or change their
plan; they edit only their content + capabilities (+ their own lead routing email).
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    get_lead_store,
    get_partner_registry,
    require_manufacturer,
)
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.leads import LeadStore
from sealai_v2.knowledge.hersteller_partner import HerstellerPartner

router = APIRouter(prefix="/api/v2/partner", tags=["partner-self"])


class PartnerSelfUpdate(BaseModel):
    """The manufacturer-editable subset. ``aktiv`` / ``plan`` / ``partner_seit`` / ``hersteller`` are
    NOT here — those are owner-controlled (paid membership). ``lead_email`` IS editable (the
    manufacturer's own routing target)."""

    firmenname: str = Field(default="", max_length=255)
    lead_email: str = Field(default="", max_length=320)
    website: str = Field(default="", max_length=500)
    beschreibung: str = ""
    standort: str = Field(default="", max_length=255)
    kontakt_oeffentlich: str = Field(default="", max_length=320)
    werkstoffe: list[str] = Field(default_factory=list)
    bauformen: list[str] = Field(default_factory=list)
    groessen: str = Field(default="", max_length=255)
    zertifikate: list[str] = Field(default_factory=list)


def _self_dict(p: HerstellerPartner) -> dict:
    # The manufacturer sees their full record incl. the owner-controlled fields (aktiv/plan), but those
    # are READ-ONLY in the UI — returned so they can see their membership status.
    return {
        "hersteller": p.hersteller,
        "firmenname": p.firmenname,
        "aktiv": p.aktiv,
        "lead_email": p.lead_email,
        "website": p.website,
        "beschreibung": p.beschreibung,
        "standort": p.standort,
        "kontakt_oeffentlich": p.kontakt_oeffentlich,
        "partner_seit": p.partner_seit,
        "plan": p.plan,
        "werkstoffe": list(p.werkstoffe),
        "bauformen": list(p.bauformen),
        "groessen": p.groessen,
        "zertifikate": list(p.zertifikate),
    }


@router.get("/me")
def get_me(
    identity: VerifiedIdentity = Depends(require_manufacturer),
    registry=Depends(get_partner_registry),
) -> dict:
    p = registry.get(identity.hersteller_id)
    if p is None:
        # The owner has not onboarded this manufacturer yet — fail-closed, no auto-create.
        raise HTTPException(status_code=404, detail="kein Partnerprofil angelegt")
    return _self_dict(p)


@router.put("/me")
def update_me(
    body: PartnerSelfUpdate,
    identity: VerifiedIdentity = Depends(require_manufacturer),
    registry=Depends(get_partner_registry),
) -> dict:
    existing = registry.get(identity.hersteller_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="kein Partnerprofil angelegt")
    # Merge ONLY the manufacturer-editable fields; aktiv/plan/partner_seit/hersteller are PRESERVED from
    # the existing record (owner-controlled paid membership — a manufacturer can never self-activate).
    updated = replace(
        existing,
        firmenname=body.firmenname,
        lead_email=body.lead_email,
        website=body.website,
        beschreibung=body.beschreibung,
        standort=body.standort,
        kontakt_oeffentlich=body.kontakt_oeffentlich,
        werkstoffe=tuple(body.werkstoffe),
        bauformen=tuple(body.bauformen),
        groessen=body.groessen,
        zertifikate=tuple(body.zertifikate),
    )
    registry.upsert(updated)
    return _self_dict(updated)


@router.get("/me/leads")
def my_leads(
    identity: VerifiedIdentity = Depends(require_manufacturer),
    leads: LeadStore = Depends(get_lead_store),
) -> dict:
    """The manufacturer's OWN leads (the RFQ briefings routed to them), newest first. The user's
    internal tenant/session ids are NOT exposed — only the briefing + metadata."""
    rows = leads.list_for_partner(identity.hersteller_id)
    return {
        "leads": [
            {
                "id": ld.id,
                "firmenname": ld.firmenname,
                "briefing_title": ld.briefing_title,
                "briefing_body": ld.briefing_body,
                "created_at": ld.created_at,
                "status": ld.status,
            }
            for ld in rows
        ]
    }
