"""Alternativen/Hersteller (Modus F, Dim. 6) — store neutrality, capability match, operation.

Neutrality is sacred (§3.9): ordering is capability-then-alphabetical, never payment; a payment/
ranking field on an entry is a load error. The shipped seed is EMPTY (owner-provided market data),
so Modus F honestly reports "no grounded data" + the neutral selection approach until curated.
"""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, ModelConfig, PipelineResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.hersteller import (
    HerstellerCatalog,
    HerstellerFaehigkeit,
    InProcessHerstellerStore,
    _entry,
    load_hersteller,
)
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def _f(fid, name, werkstoffe, bauformen):
    return HerstellerFaehigkeit(
        id=fid,
        hersteller=name,
        werkstoffe=tuple(werkstoffe),
        bauformen=tuple(bauformen),
        groessen="",
        zertifikate=(),
        review_state="draft",
        provenance=("draft:test",),
    )


def _store(*entries):
    return InProcessHerstellerStore(HerstellerCatalog(faehigkeiten=tuple(entries)))


def test_shipped_seed_is_empty():
    assert (
        len(load_hersteller().faehigkeiten) == 0
    )  # owner-provided, not model-generated


def test_query_matches_by_capability_and_orders_neutral():
    # equal capability match → ALPHABETICAL tie-break (neutral), never payment
    store = _store(
        _f("H1", "Zeta Seals", ["FKM", "NBR"], ["RWDR"]),
        _f("H2", "Alpha Dicht", ["FKM"], ["RWDR"]),
    )
    res = store.query(tenant_id="t1", material="FKM", bauform="RWDR")
    assert [f.hersteller for f in res] == ["Alpha Dicht", "Zeta Seals"]


def test_capability_filters_out_nonmatch():
    store = _store(_f("H1", "Alpha", ["EPDM"], ["O-Ring"]))
    assert store.query(tenant_id="t1", material="FKM", bauform="RWDR") == ()


def test_neutrality_guard_rejects_payment_field():
    with pytest.raises(ValueError, match="pay-to-rank|Bezahlung"):
        _entry(
            {
                "id": "X",
                "hersteller": "Y",
                "review_state": "draft",
                "provenance": ["draft:t"],
                "rank": 1,
            }
        )


def test_stage_empty_seed_reports_no_grounded_data():
    v = stages.alternativen(
        InProcessHerstellerStore(),
        "Wer kann einen RWDR aus FKM noch herstellen?",
        tenant_id="t1",
    )
    assert v is not None
    assert v["grounded_data"] is False
    assert "Bezahlung" in v["neutralitaet"]


def test_p17_empty_hersteller_store_invents_no_manufacturer():
    # P1.7 — deterministic guard for Modus F's headline doctrine ("never invents firm names").
    # STRUCTURAL guarantee at the STAGE boundary: with the empty Dim.6 store, alternativen(...)
    # MUST report grounded_data=False AND its structured output must name ZERO manufacturers — the
    # capability list is absent/empty, so there is no firm name for L1 to relay. (The L1-NARRATION
    # guarantee — that the prose itself invents no firm — remains measured by the eval REPLAY; this
    # test pins only what the backend deterministically controls: the stage's structured output.)
    v = stages.alternativen(
        InProcessHerstellerStore(),  # empty shipped seed
        "Wer kann einen RWDR aus FKM noch herstellen? Nenne vergleichbare Hersteller.",
        tenant_id="t1",
    )
    assert v is not None
    assert v["grounded_data"] is False
    # the manufacturer list is the ONLY field that may carry a firm name — it must be empty/absent
    assert v.get("hersteller", []) == []
    assert (
        "ordered_by" not in v
    )  # the capability-ranking field only exists with grounded makers


def test_stage_none_without_alternatives_keyword():
    assert (
        stages.alternativen(InProcessHerstellerStore(), "Was kann FKM?", tenant_id="t1")
        is None
    )


def test_stage_with_curated_data_returns_makers_neutral():
    store = _store(_f("H1", "Alpha Dicht", ["FKM"], ["RWDR"]))
    v = stages.alternativen(store, "Wer macht RWDR aus FKM?", tenant_id="t1")
    assert v["grounded_data"] is True
    assert v["hersteller"] == ["Alpha Dicht"]
    assert v["ordered_by"] == "capability"


def _pipeline(client):
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        hersteller=InProcessHerstellerStore(),
    )


def test_alternativen_flows_to_result_empty_honest():
    res = asyncio.run(
        _pipeline(FakeLlmClient("Antwort")).run(
            "Wer kann das noch herstellen, RWDR aus FKM?", tenant=TenantContext("t1")
        )
    )
    assert res.alternativen is not None and res.alternativen["grounded_data"] is False


def test_serializer_surfaces_alternativen():
    out = chat_response(
        PipelineResult(
            question="x",
            tenant_id="t1",
            flags=Flags(),
            understanding=None,
            answer=Answer(text="…", model="fake"),
            alternativen={"grounded_data": False, "neutralitaet": "…"},
        )
    )
    assert out["alternativen"]["grounded_data"] is False
