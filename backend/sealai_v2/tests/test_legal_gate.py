"""require_legal_acceptance (Legal-by-Design Phase B, Goal 3) wired onto the productive surface —
chat / chat-stream / briefing / compute / anfrage. Two things must both hold:

1. Default (``legal_gate_enabled=False``, the shipped default): every route behaves BYTE-IDENTICAL
   to before this patch — no acceptance row needed at all. Regression coverage for the "OFF is a
   true no-op" claim in ``api/deps.py``'s docstring.
2. Enabled: every route 403s without a CURRENT (version-matching) acceptance row, and works once
   one exists. A stale (pre-doctrine-bump) acceptance does NOT count.
"""

from __future__ import annotations

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.legal_doctrine import doctrine_payload
from sealai_v2.db.legal_acceptance import InProcessLegalAcceptanceStore, LegalAcceptance
from sealai_v2.db.leads import InProcessLeadStore
from sealai_v2.knowledge.hersteller_partner import (
    HerstellerPartner,
    InProcessPartnerRegistry,
)
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.tests._apiutil import auth, make_client
from sealai_v2.tests._fakes import FakeLlmClient


def _base_client(*, gate_enabled: bool, pipeline: Pipeline | None = None, store=None):
    client, pipeline = make_client(pipeline=pipeline)
    store = store if store is not None else InProcessLegalAcceptanceStore()
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        legal_gate_enabled=gate_enabled
    )
    app.dependency_overrides[deps.get_legal_acceptance_store] = lambda: store
    return client, pipeline, store


def _current_acceptance(tenant_id: str = "tenant-A") -> LegalAcceptance:
    d = doctrine_payload()
    return LegalAcceptance(
        tenant_id=tenant_id,
        company_name="ACME Dichtungen GmbH",
        business_email="einkauf@acme-dichtungen.example",
        role="Einkauf",
        vat_id="DE123456789",
        legal_basis_accepted=True,
        dpa_accepted=True,
        business_user_confirmed=True,
        accepted_terms_version=d["terms_version"],
        accepted_privacy_version=d["privacy_version"],
        accepted_dpa_version=d["dpa_version"],
        accepted_at="2026-07-08T10:00:00+00:00",
    )


# --- default OFF: byte-identical, no acceptance row anywhere ---


def test_chat_works_without_acceptance_when_gate_is_off():
    client, _, _ = _base_client(gate_enabled=False)
    r = client.post("/api/v2/chat", json={"message": "x"}, headers=auth("tok-A"))
    assert r.status_code == 200


def test_briefing_works_without_acceptance_when_gate_is_off():
    client, _, _ = _base_client(gate_enabled=False)
    r = client.post("/api/v2/briefing", json={"message": "x"}, headers=auth("tok-A"))
    assert r.status_code == 200


def test_compute_works_without_acceptance_when_gate_is_off():
    engine_client = FakeLlmClient("ok")
    pipeline = Pipeline(
        generator=L1Generator(engine_client, PromptAssembler(), ModelConfig("fake-l1")),
        client=engine_client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
    )
    client, _, _ = _base_client(gate_enabled=False, pipeline=pipeline)
    r = client.get("/api/v2/compute", headers=auth("tok-A"))
    assert r.status_code == 200


# --- enabled: fail-closed without a current acceptance ---


def test_chat_is_blocked_without_any_acceptance_when_gate_is_on():
    client, _, _ = _base_client(gate_enabled=True)
    r = client.post("/api/v2/chat", json={"message": "x"}, headers=auth("tok-A"))
    assert r.status_code == 403
    assert r.json()["detail"] == "legal_acceptance_required"


def test_chat_succeeds_once_a_current_acceptance_exists():
    store = InProcessLegalAcceptanceStore()
    store.upsert(_current_acceptance("tenant-A"))
    client, _, _ = _base_client(gate_enabled=True, store=store)
    r = client.post("/api/v2/chat", json={"message": "x"}, headers=auth("tok-A"))
    assert r.status_code == 200


def test_stale_acceptance_version_still_blocks():
    store = InProcessLegalAcceptanceStore()
    import dataclasses

    stale = dataclasses.replace(_current_acceptance("tenant-A"), accepted_terms_version="old-v0")
    store.upsert(stale)
    client, _, _ = _base_client(gate_enabled=True, store=store)
    r = client.post("/api/v2/chat", json={"message": "x"}, headers=auth("tok-A"))
    assert r.status_code == 403


def test_acceptance_does_not_cross_the_tenant_boundary():
    store = InProcessLegalAcceptanceStore()
    store.upsert(_current_acceptance("tenant-A"))  # only tenant-A accepted
    client, _, _ = _base_client(gate_enabled=True, store=store)
    r = client.post("/api/v2/chat", json={"message": "x"}, headers=auth("tok-B"))
    assert r.status_code == 403


def test_briefing_is_gated_too():
    client, _, _ = _base_client(gate_enabled=True)
    r = client.post("/api/v2/briefing", json={"message": "x"}, headers=auth("tok-A"))
    assert r.status_code == 403


def test_compute_is_gated_too():
    engine_client = FakeLlmClient("ok")
    pipeline = Pipeline(
        generator=L1Generator(engine_client, PromptAssembler(), ModelConfig("fake-l1")),
        client=engine_client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
    )
    client, _, _ = _base_client(gate_enabled=True, pipeline=pipeline)
    r = client.get("/api/v2/compute", headers=auth("tok-A"))
    assert r.status_code == 403


def test_anfrage_is_gated_too():
    fake = FakeLlmClient("ok")
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
    pipeline = Pipeline(
        generator=L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1")),
        client=fake,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=InProcessRetriever(),
        partner_registry=InProcessPartnerRegistry((partner,)),
    )
    client, _, _ = _base_client(gate_enabled=True, pipeline=pipeline)
    app.dependency_overrides[deps.get_lead_store] = lambda: InProcessLeadStore()
    r = client.post(
        "/api/v2/anfrage",
        json={"partner_id": "acme", "message": "x"},
        headers=auth("tok-A"),
    )
    assert r.status_code == 403


def test_doctrine_and_acceptance_endpoints_are_never_gated_by_themselves():
    # A tenant with zero acceptance must still be able to READ the doctrine and SUBMIT an
    # acceptance — gating those would make the gate impossible to clear.
    client, _, _ = _base_client(gate_enabled=True)
    assert client.get("/api/v2/legal/doctrine").status_code == 200
    d = doctrine_payload()
    r = client.post(
        "/api/v2/legal/acceptance",
        json={
            "company_name": "ACME Dichtungen GmbH",
            "business_email": "einkauf@acme-dichtungen.example",
            "role": "Einkauf",
            "vat_id": "",
            "legal_basis_accepted": True,
            "dpa_accepted": True,
            "business_user_confirmed": True,
            "terms_version": d["terms_version"],
            "privacy_version": d["privacy_version"],
            "dpa_version": d["dpa_version"],
        },
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
