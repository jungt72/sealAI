"""Admin surface for the Hersteller-Partner pool (owner business model) — the dashboard-editable CRUD
(manage paying partners) + lead retrieval (the captured Anfragen, so the owner can forward them to the
manufacturers). EVERY endpoint requires the platform-owner realm-role (``require_platform_owner``, P0 fail-closed); the
gate is ADDITIVE over the verified token — tenant isolation is untouched.

This is the OWNER surface, so ``lead_email`` IS returned here (the routing target the owner needs) —
unlike the user-facing /anfrage, which never exposes it. Neutrality keystone: ``plan`` is stored +
editable here (billing metadata) but is NEVER read by the selection (``rank_partners`` ranks purely by
capability fit). The owner manages MEMBERSHIP; the pool ranks itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    get_lead_store,
    get_partner_registry,
    require_platform_owner,
)
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.leads import LeadStore
from sealai_v2.knowledge.hersteller_partner import HerstellerPartner

router = APIRouter(prefix="/api/v2/admin", tags=["hersteller-admin"])


class PartnerIn(BaseModel):
    """The dashboard-editable partner record. ``hersteller`` (the stable id) is the path param, not a
    body field. ``aktiv`` gates pool MEMBERSHIP (a paying partner); it never affects ranking order."""

    firmenname: str = Field(default="", max_length=255)
    aktiv: bool = False
    lead_email: str = Field(default="", max_length=320)
    website: str = Field(default="", max_length=500)
    beschreibung: str = ""
    standort: str = Field(default="", max_length=255)
    kontakt_oeffentlich: str = Field(default="", max_length=320)
    partner_seit: str = Field(default="", max_length=32)
    plan: str = Field(
        default="", max_length=64
    )  # billing metadata — NEVER a ranking input (§3.9)
    werkstoffe: list[str] = Field(default_factory=list)
    bauformen: list[str] = Field(default_factory=list)
    groessen: str = Field(default="", max_length=255)
    zertifikate: list[str] = Field(default_factory=list)


def _partner_dict(p: HerstellerPartner) -> dict:
    return {
        "hersteller": p.hersteller,
        "firmenname": p.firmenname,
        "aktiv": p.aktiv,
        "lead_email": p.lead_email,  # OWNER surface — the routing target IS shown here
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


@router.get("/hersteller")
def list_partners(
    _: VerifiedIdentity = Depends(require_platform_owner),
    registry=Depends(get_partner_registry),
) -> dict:
    return {"hersteller": [_partner_dict(p) for p in registry.list_all()]}


@router.get("/hersteller/{hersteller_id}")
def get_partner(
    hersteller_id: str,
    _: VerifiedIdentity = Depends(require_platform_owner),
    registry=Depends(get_partner_registry),
) -> dict:
    p = registry.get(hersteller_id)
    if p is None:
        raise HTTPException(status_code=404, detail="hersteller nicht gefunden")
    return _partner_dict(p)


@router.put("/hersteller/{hersteller_id}")
def upsert_partner(
    hersteller_id: str,
    body: PartnerIn,
    _: VerifiedIdentity = Depends(require_platform_owner),
    registry=Depends(get_partner_registry),
) -> dict:
    partner = HerstellerPartner(
        hersteller=hersteller_id,
        firmenname=body.firmenname,
        aktiv=body.aktiv,
        lead_email=body.lead_email,
        website=body.website,
        beschreibung=body.beschreibung,
        standort=body.standort,
        kontakt_oeffentlich=body.kontakt_oeffentlich,
        partner_seit=body.partner_seit,
        plan=body.plan,
        werkstoffe=tuple(body.werkstoffe),
        bauformen=tuple(body.bauformen),
        groessen=body.groessen,
        zertifikate=tuple(body.zertifikate),
    )
    registry.upsert(partner)
    return _partner_dict(partner)


@router.delete("/hersteller/{hersteller_id}")
def delete_partner(
    hersteller_id: str,
    _: VerifiedIdentity = Depends(require_platform_owner),
    registry=Depends(get_partner_registry),
) -> dict:
    if not registry.delete(hersteller_id):
        raise HTTPException(status_code=404, detail="hersteller nicht gefunden")
    return {"deleted": hersteller_id}


@router.get("/leads")
def list_leads(
    _: VerifiedIdentity = Depends(require_platform_owner),
    leads: LeadStore = Depends(get_lead_store),
    partner_id: str | None = None,
) -> dict:
    """The captured Anfragen (owner surface) — newest first. Optionally filtered to one partner. The
    full briefing + the routing ``lead_email`` are included so the owner can forward / track each lead."""
    rows = leads.list_for_partner(partner_id) if partner_id else leads.list_all()
    return {
        "leads": [
            {
                "id": ld.id,
                "partner_id": ld.partner_id,
                "firmenname": ld.firmenname,
                "lead_email": ld.lead_email,
                "tenant_id": ld.tenant_id,
                "session_id": ld.session_id,
                "briefing_title": ld.briefing_title,
                "briefing_body": ld.briefing_body,
                "created_at": ld.created_at,
                "status": ld.status,
            }
            for ld in rows
        ]
    }
