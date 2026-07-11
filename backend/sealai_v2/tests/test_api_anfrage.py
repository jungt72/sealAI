"""POST /api/v2/anfrage — the lead-gen action (owner business model). Proves: a briefing is rendered
from the session + a durable lead is captured for a PAYING (aktiv) partner; the internal ``lead_email``
is NEVER returned; unknown/inactive partners capture nothing (404); auth is required (P0)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import ModelConfig, VerifiedIdentity
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.db.leads import InProcessLeadStore
from sealai_v2.knowledge.hersteller_partner import (
    HerstellerPartner,
    InProcessPartnerRegistry,
)
from sealai_v2.knowledge.manufacturer_capability import (
    InProcessManufacturerCapabilityStore,
    ManufacturerCapabilityProfile,
)
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.auth import FakeAuthValidator
from sealai_v2.tests._fakes import FakeLlmClient

IDS = {"tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A")}


def _partner(hersteller="acme", *, aktiv=True):
    return HerstellerPartner(
        hersteller=hersteller,
        firmenname="ACME Dichtungen GmbH",
        aktiv=aktiv,
        lead_email="leads@acme.example",
        website="https://acme.example",
        beschreibung="RWDR-Spezialist",
        standort="DE",
        werkstoffe=("FKM",),
        bauformen=("RWDR",),
    )


def _client(*partners, handoff_enabled=True, capability_status="verified"):
    client = FakeLlmClient("Antwort.")
    commercial_registry = InProcessPartnerRegistry(tuple(partners))
    pipeline = Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=InProcessRetriever(),
        partner_registry=commercial_registry,
    )
    profiles = tuple(
        ManufacturerCapabilityProfile(
            manufacturer_id=partner.hersteller,
            company_name=partner.firmenname,
            status=capability_status,
            seal_types=partner.bauformen,
            materials=partner.werkstoffe,
            evidence=({"citation": "reviewed test evidence"},)
            if capability_status == "verified"
            else (),
            review_expires_at="2099-01-01T00:00:00Z"
            if capability_status == "verified"
            else "",
        )
        for partner in partners
    )
    capability_store = InProcessManufacturerCapabilityStore(profiles)
    store = InProcessLeadStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDS)
    app.dependency_overrides[deps.get_pipeline] = lambda: pipeline
    app.dependency_overrides[deps.get_lead_store] = lambda: store
    app.dependency_overrides[deps.get_partner_registry] = lambda: commercial_registry
    app.dependency_overrides[deps.get_capability_store] = lambda: capability_store
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        capability_profiles_enabled=handoff_enabled,
        manufacturer_fit_enabled=handoff_enabled,
        manufacturer_handoff_enabled=handoff_enabled,
    )
    return TestClient(app), store


def _auth(token="tok-A"):
    return {"Authorization": f"Bearer {token}"}


def test_anfrage_captures_lead_and_returns_briefing():
    client, store = _client(_partner("acme"))
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "message": "FKM RWDR bei 150°C?"},
        headers=_auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "captured"
    assert body["partner"]["firmenname"] == "ACME Dichtungen GmbH"
    assert body["briefing"]["title"] and body["briefing"]["body"]
    # P3: the briefing carries its knowledge-catalog state (empty here — this pipeline is
    # hand-built, not build_pipeline()'d, so no catalog versions were wired).
    assert body["briefing"]["wissensstand"] == ""
    leads = store.list_for_partner("acme")
    assert len(leads) == 1
    assert leads[0].lead_email == "leads@acme.example"  # routed internally
    assert leads[0].tenant_id == "tenant-A" and leads[0].session_id == "sess-A"
    assert leads[0].briefing_body  # the worked-out situation was captured


def test_anfrage_never_exposes_lead_email():
    client, _ = _client(_partner("acme"))
    r = client.post(
        "/api/v2/anfrage", json={"partner_id": "acme", "message": "x"}, headers=_auth()
    )
    assert r.status_code == 200
    assert (
        "leads@acme.example" not in r.text
    )  # internal routing field is never returned


def test_anfrage_unknown_partner_404_captures_nothing():
    client, store = _client(_partner("acme"))
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "ghost", "message": "x"},
        headers=_auth(),
    )
    assert r.status_code == 404
    assert store.list_all() == ()


def test_anfrage_inactive_partner_404_captures_nothing():
    # A non-paying (inactive) partner receives no lead — payment gates pool membership.
    client, store = _client(_partner("acme", aktiv=False))
    r = client.post(
        "/api/v2/anfrage", json={"partner_id": "acme", "message": "x"}, headers=_auth()
    )
    assert r.status_code == 404
    assert store.list_all() == ()


def test_anfrage_requires_auth():
    client, _ = _client(_partner("acme"))
    r = client.post("/api/v2/anfrage", json={"partner_id": "acme", "message": "x"})
    assert r.status_code == 401


def test_anfrage_fails_closed_while_handoff_mode_is_inactive():
    client, store = _client(_partner("acme"), handoff_enabled=False)
    response = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "message": "x"},
        headers=_auth(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["mode"] == "manufacturer_handoff"
    assert store.list_all() == ()


def test_anfrage_rejects_unverified_capability_profile():
    client, store = _client(_partner("acme"), capability_status="submitted")
    response = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "message": "x"},
        headers=_auth(),
    )

    assert response.status_code == 404
    assert store.list_all() == ()
