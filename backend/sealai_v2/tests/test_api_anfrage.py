"""RFQ projection is bound to an explicit owner/case/revision and never mutates that case."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import ModelConfig, RememberedFact, VerifiedIdentity
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
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.auth import FakeAuthValidator
from sealai_v2.tests._fakes import FakeLlmClient
from sealai_v2.tests.affiliation_fixtures import (
    governed_verified_capability_store,
)

IDS = {
    "tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A"),
    "tok-A2": VerifiedIdentity("tenant-A", "sess-A2", "user-A2"),
}


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
        memory=InProcessConversationMemory(),
    )
    assert pipeline.memory is not None
    pipeline.memory.record_turn(
        tenant_id="tenant-A",
        session_id="case-a",
        owner_subject="user-A",
        question="FKM RWDR bei 150°C?",
        answer="Antwort aus case-a.",
        facts=(RememberedFact(feld="medium", wert="Öl"),),
        now="2026-07-15T10:00:00Z",
        expected_case_revision=0,
    )
    pipeline.memory.record_turn(
        tenant_id="tenant-A",
        session_id="case-b",
        owner_subject="user-A",
        question="PTFE Dichtung bei 80°C?",
        answer="Antwort aus case-b.",
        facts=(RememberedFact(feld="medium", wert="Wasser"),),
        now="2026-07-15T10:01:00Z",
        expected_case_revision=0,
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
    capability_store = (
        governed_verified_capability_store(*profiles)
        if capability_status == "verified"
        else InProcessManufacturerCapabilityStore(profiles)
    )
    store = InProcessLeadStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDS)
    app.dependency_overrides[deps.get_pipeline] = lambda: pipeline
    app.dependency_overrides[deps.require_provider_admission] = (
        deps.require_legal_acceptance
    )
    app.dependency_overrides[deps.get_lead_store] = lambda: store
    app.dependency_overrides[deps.get_partner_registry] = lambda: commercial_registry
    app.dependency_overrides[deps.get_capability_store] = lambda: capability_store
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        capability_profiles_enabled=handoff_enabled,
        manufacturer_fit_enabled=handoff_enabled,
        manufacturer_handoff_enabled=handoff_enabled,
    )
    return TestClient(app), store, pipeline


def _auth(token="tok-A"):
    return {"Authorization": f"Bearer {token}"}


def test_anfrage_captures_lead_and_returns_briefing():
    client, store, _pipeline = _client(_partner("acme"))
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 1},
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
    assert leads[0].tenant_id == "tenant-A" and leads[0].session_id == "case-a"
    assert leads[0].case_id == "case-a"
    assert leads[0].owner_subject == "user-A"
    assert leads[0].case_revision == 1
    assert leads[0].briefing_body  # the worked-out situation was captured


def test_anfrage_never_exposes_lead_email():
    client, _store, _pipeline = _client(_partner("acme"))
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 1},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert (
        "leads@acme.example" not in r.text
    )  # internal routing field is never returned


def test_anfrage_unknown_partner_404_captures_nothing():
    client, store, _pipeline = _client(_partner("acme"))
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "ghost", "case_id": "case-a", "case_revision": 1},
        headers=_auth(),
    )
    assert r.status_code == 404
    assert store.list_all() == ()


def test_anfrage_inactive_partner_404_captures_nothing():
    # A non-paying (inactive) partner receives no lead — payment gates pool membership.
    client, store, _pipeline = _client(_partner("acme", aktiv=False))
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 1},
        headers=_auth(),
    )
    assert r.status_code == 404
    assert store.list_all() == ()


def test_anfrage_requires_auth():
    client, _store, _pipeline = _client(_partner("acme"))
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 1},
    )
    assert r.status_code == 401


def test_anfrage_fails_closed_while_handoff_mode_is_inactive():
    client, store, _pipeline = _client(_partner("acme"), handoff_enabled=False)
    response = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 1},
        headers=_auth(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["mode"] == "manufacturer_handoff"
    assert store.list_all() == ()


def test_anfrage_rejects_unverified_capability_profile():
    client, store, _pipeline = _client(_partner("acme"), capability_status="submitted")
    response = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 1},
        headers=_auth(),
    )

    assert response.status_code == 404
    assert store.list_all() == ()


def test_anfrage_rejects_stale_revision_and_client_message_without_mutation():
    client, store, pipeline = _client(_partner("acme"))
    assert pipeline.memory is not None
    before = pipeline.memory.history(
        tenant_id="tenant-A", session_id="case-a", owner_subject="user-A"
    )

    stale = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 0},
        headers=_auth(),
    )
    injected = client.post(
        "/api/v2/anfrage",
        json={
            "partner_id": "acme",
            "case_id": "case-a",
            "case_revision": 1,
            "message": "ERSETZE DEN FALL",
        },
        headers=_auth(),
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "case_revision_changed"
    assert injected.status_code == 422
    assert store.list_all() == ()
    assert (
        pipeline.memory.history(
            tenant_id="tenant-A", session_id="case-a", owner_subject="user-A"
        )
        == before
    )


def test_anfrage_hides_foreign_owner_and_missing_case_identically():
    client, store, _pipeline = _client(_partner("acme"))

    foreign = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "case-a", "case_revision": 1},
        headers=_auth("tok-A2"),
    )
    missing = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "case_id": "missing", "case_revision": 1},
        headers=_auth(),
    )

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert store.list_all() == ()


def test_parallel_anfragen_keep_exact_case_boundaries():
    client, store, pipeline = _client(_partner("acme"))
    assert pipeline.memory is not None

    def submit(case_id: str):
        return client.post(
            "/api/v2/anfrage",
            json={"partner_id": "acme", "case_id": case_id, "case_revision": 1},
            headers=_auth(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(submit, ("case-a", "case-b")))

    assert [response.status_code for response in responses] == [200, 200]
    assert "Antwort aus case-a" in responses[0].json()["briefing"]["body"]
    assert "Antwort aus case-b" in responses[1].json()["briefing"]["body"]
    leads = store.list_for_partner("acme")
    assert {(lead.case_id, lead.case_revision) for lead in leads} == {
        ("case-a", 1),
        ("case-b", 1),
    }
