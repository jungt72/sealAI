"""Manufacturer SELF-SERVICE /api/v2/partner/me — scoped to identity.hersteller_id (there is no id
param to abuse). Proves: the manufacturer role + a hersteller_id claim are required; the manufacturer
edits content but CANNOT change the owner-controlled aktiv/plan/partner_seit (the critical paid-
membership boundary); they see only their OWN leads, without the user's internal ids."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.leads import InProcessLeadStore, Lead
from sealai_v2.knowledge.hersteller_partner import (
    HerstellerPartner,
    InProcessPartnerRegistry,
)
from sealai_v2.security.auth import FakeAuthValidator

IDS = {
    "tok-mfg": VerifiedIdentity(
        "t", "s", "mfg-user", roles=("manufacturer",), hersteller_id="acme"
    ),
    "tok-mfg-noid": VerifiedIdentity(
        "t", "s", "mfg2", roles=("manufacturer",), hersteller_id=""
    ),
    "tok-user": VerifiedIdentity("t2", "s2", "user"),  # no roles
}


def _acme():
    return HerstellerPartner(
        hersteller="acme",
        firmenname="ACME GmbH",
        aktiv=True,
        lead_email="leads@acme",
        plan="enterprise",
        website="https://acme",
        beschreibung="alt",
        standort="DE",
        partner_seit="2026",
        werkstoffe=("FKM",),
        bauformen=("RWDR",),
    )


def _client(*partners, store=None):
    reg = InProcessPartnerRegistry(tuple(partners))
    store = store if store is not None else InProcessLeadStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDS)
    app.dependency_overrides[deps.get_partner_registry] = lambda: reg
    app.dependency_overrides[deps.get_lead_store] = lambda: store
    return TestClient(app), reg, store


def _mfg():
    return {"Authorization": "Bearer tok-mfg"}


def test_requires_manufacturer_role():
    client, _, _ = _client(_acme())
    r = client.get("/api/v2/partner/me", headers={"Authorization": "Bearer tok-user"})
    assert r.status_code == 403


def test_requires_hersteller_id_claim():
    client, _, _ = _client(_acme())
    r = client.get(
        "/api/v2/partner/me", headers={"Authorization": "Bearer tok-mfg-noid"}
    )
    assert r.status_code == 403


def test_requires_auth():
    client, _, _ = _client(_acme())
    assert client.get("/api/v2/partner/me").status_code == 401


def test_get_me_returns_own_record():
    client, _, _ = _client(_acme())
    r = client.get("/api/v2/partner/me", headers=_mfg())
    assert r.status_code == 200
    assert r.json()["hersteller"] == "acme" and r.json()["plan"] == "enterprise"


def test_get_me_404_when_no_profile():
    client, _, _ = (
        _client()
    )  # empty registry → owner hasn't onboarded this manufacturer
    assert client.get("/api/v2/partner/me", headers=_mfg()).status_code == 404


def test_update_me_edits_content_but_preserves_owner_fields():
    client, reg, _ = _client(_acme())
    r = client.put(
        "/api/v2/partner/me",
        headers=_mfg(),
        json={
            "firmenname": "ACME neu",
            "lead_email": "neu@acme",
            "beschreibung": "neu",
            "werkstoffe": ["FKM", "EPDM"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["firmenname"] == "ACME neu" and body["werkstoffe"] == ["FKM", "EPDM"]
    # THE CRITICAL BOUNDARY: owner-controlled membership fields are PRESERVED, never settable here.
    assert body["aktiv"] is True
    assert body["plan"] == "enterprise"
    assert body["partner_seit"] == "2026"
    # persisted with the boundary intact
    assert reg.get("acme").firmenname == "ACME neu"
    assert reg.get("acme").aktiv is True and reg.get("acme").plan == "enterprise"


def test_update_me_404_when_no_profile():
    client, _, _ = _client()
    assert client.put("/api/v2/partner/me", headers=_mfg(), json={}).status_code == 404


def test_my_leads_scoped_to_own_and_no_internal_ids():
    store = InProcessLeadStore()
    for pid in ("acme", "beta"):
        store.store(
            Lead(
                partner_id=pid,
                firmenname=pid,
                lead_email=f"l@{pid}",
                tenant_id="t",
                session_id="s",
                briefing_title="T",
                briefing_body="B",
                created_at="2026",
            )
        )
    client, _, _ = _client(_acme(), store=store)
    leads = client.get("/api/v2/partner/me/leads", headers=_mfg()).json()["leads"]
    assert len(leads) == 1 and leads[0]["briefing_body"] == "B"  # only acme's leads
    assert (
        "tenant_id" not in leads[0] and "session_id" not in leads[0]
    )  # internal ids hidden
