"""risk_flags surfaced on the chat/briefing/anfrage API responses (Legal-by-Design Phase D)."""

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
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.knowledge.manufacturer_capability import (
    InProcessManufacturerCapabilityStore,
    ManufacturerCapabilityProfile,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.auth import FakeAuthValidator
from sealai_v2.tests._apiutil import auth, make_client
from sealai_v2.tests._fakes import FakeLlmClient

_IDS = {"tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A")}


def test_chat_response_carries_matched_risk_flags():
    client, _ = make_client()
    r = client.post(
        "/api/v2/chat",
        json={"message": "Ist FKM für ATEX-Zonen geeignet?"},
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
    assert r.json()["risk_flags"] == ["ATEX"]


def test_chat_response_risk_flags_empty_when_no_match():
    client, _ = make_client()
    r = client.post(
        "/api/v2/chat",
        json={"message": "Welches Material für Hydrauliköl bei 80°C?"},
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
    assert r.json()["risk_flags"] == []


def test_briefing_response_carries_risk_flags():
    client, _ = make_client(pipeline=None)
    r = client.post(
        "/api/v2/briefing",
        json={"message": "Ist FKM für ATEX-Zonen geeignet?"},
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
    assert r.json()["risk_flags"] == ["ATEX"]


def test_anfrage_response_briefing_carries_risk_flags():
    fake = FakeLlmClient("Antwort.")
    partner = HerstellerPartner(
        hersteller="acme",
        firmenname="ACME Dichtungen GmbH",
        aktiv=True,
        lead_email="leads@acme.example",
        website="https://acme.example",
        beschreibung="RWDR-Spezialist",
        standort="DE",
        werkstoffe=("FKM",),
        bauformen=("RWDR",),
    )
    commercial_registry = InProcessPartnerRegistry((partner,))
    pipeline = Pipeline(
        generator=L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1")),
        client=fake,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=InProcessRetriever(),
        partner_registry=commercial_registry,
    )
    capability_store = InProcessManufacturerCapabilityStore(
        (
            ManufacturerCapabilityProfile(
                manufacturer_id="acme",
                company_name="ACME Dichtungen GmbH",
                status="verified",
                seal_types=("RWDR",),
                materials=("FKM",),
                evidence=({"citation": "reviewed test evidence"},),
                review_expires_at="2099-01-01T00:00:00Z",
            ),
        )
    )
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(_IDS)
    app.dependency_overrides[deps.get_pipeline] = lambda: pipeline
    app.dependency_overrides[deps.get_lead_store] = lambda: InProcessLeadStore()
    app.dependency_overrides[deps.get_partner_registry] = lambda: commercial_registry
    app.dependency_overrides[deps.get_capability_store] = lambda: capability_store
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        capability_profiles_enabled=True,
        manufacturer_fit_enabled=True,
        manufacturer_handoff_enabled=True,
    )
    client = TestClient(app)
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "message": "Ist FKM für ATEX-Zonen geeignet?"},
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
    assert r.json()["briefing"]["risk_flags"] == ["ATEX"]
