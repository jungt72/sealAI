"""risk_flags surfaced on the chat/briefing/anfrage API responses (Legal-by-Design Phase D)."""

from __future__ import annotations

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
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.knowledge.manufacturer_capability import (
    InProcessManufacturerCapabilityStore,
    ManufacturerCapabilityProfile,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.auth import FakeAuthValidator
from sealai_v2.security.lifecycle_control import InMemoryLifecycleControlStore
from sealai_v2.tests._apiutil import auth, make_client
from sealai_v2.tests._fakes import FakeLlmClient

_IDS = {"tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A")}
_POLICY = "authority:test-policy-v1"
_PURPOSE = "purpose:test-v1"
_CONSENT = "consent:test-v1"
_SECRET = "x" * 32


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
    client, pipeline = make_client(pipeline=None)
    assert pipeline.memory is not None
    pipeline.memory.record_turn(
        tenant_id="tenant-A",
        session_id="case-a",
        owner_subject="user-A",
        question="Ist FKM für ATEX-Zonen geeignet?",
        answer="Antwort.",
        facts=(RememberedFact(feld="medium", wert="Luft"),),
        expected_case_revision=0,
    )
    r = client.post(
        "/api/v2/briefing",
        json={"case_id": "case-a", "case_revision": 1},
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
        memory=InProcessConversationMemory(),
    )
    assert pipeline.memory is not None
    pipeline.memory.record_turn(
        tenant_id="tenant-A",
        session_id="case-a",
        owner_subject="user-A",
        question="Ist FKM für ATEX-Zonen geeignet?",
        answer="Antwort.",
        facts=(RememberedFact(feld="medium", wert="Luft"),),
        expected_case_revision=0,
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
    app.dependency_overrides[deps.require_provider_admission] = (
        deps.require_legal_acceptance
    )
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(_IDS)
    app.dependency_overrides[deps.get_pipeline] = lambda: pipeline
    app.dependency_overrides[deps.get_lead_store] = lambda: InProcessLeadStore(
        receipt_secret=_SECRET, policy_authority_ref=_POLICY
    )
    app.dependency_overrides[deps.get_lifecycle_control_store] = (
        lambda: InMemoryLifecycleControlStore()
    )
    app.dependency_overrides[deps.get_partner_registry] = lambda: commercial_registry
    app.dependency_overrides[deps.get_capability_store] = lambda: capability_store
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        database_url="postgresql+psycopg2://sealai_api@localhost/sealai_v2",
        database_rls_scope_enabled=True,
        api_lifecycle_enabled=True,
        api_lifecycle_policy_authority_ref=_POLICY,
        api_lifecycle_purpose_version=_PURPOSE,
        api_lifecycle_consent_version=_CONSENT,
        api_lifecycle_receipt_hmac_secret=_SECRET,
        capability_profiles_enabled=True,
        manufacturer_fit_enabled=True,
        manufacturer_handoff_enabled=True,
    )
    client = TestClient(app)
    r = client.post(
        "/api/v2/anfrage",
        json={
            "partner_id": "acme",
            "case_id": "case-a",
            "case_revision": 1,
            "governance": {
                "tenant_id": "tenant-A",
                "policy_authority_ref": _POLICY,
                "purpose_version": _PURPOSE,
                "consent_version": _CONSENT,
                "handoff_confirmed": True,
                "pii_classification": "none_declared",
                "prompt_trust": "untrusted",
            },
        },
        headers={**auth("tok-A"), "Idempotency-Key": "risk-lead-key-0001"},
    )
    assert r.status_code == 200
    assert r.json()["briefing"]["risk_flags"] == ["ATEX"]
