"""Alternativen/Hersteller (Modus F, Dim. 6) — the PARTNER POOL (owner business model): payment gates
pool MEMBERSHIP, the SELECTION ranks by capability fit (§3.9, never pay-to-rank). The capability-SEED
neutrality keystone stays structural on hersteller.py. Empty/no-match pool → honest "no partner" with
ZERO firm names (P1.7 — the backend invents none)."""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, ModelConfig, PipelineResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.hersteller import _entry, load_hersteller
from sealai_v2.knowledge.hersteller_partner import (
    HerstellerPartner,
    InProcessPartnerRegistry,
)
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def _partner(name, werkstoffe=(), bauformen=(), *, aktiv=True, plan=""):
    return HerstellerPartner(
        hersteller=name.lower().replace(" ", "-"),
        firmenname=name,
        aktiv=aktiv,
        lead_email=f"leads@{name}",
        plan=plan,
        werkstoffe=werkstoffe,
        bauformen=bauformen,
        beschreibung=f"{name} – Dichtungen",
    )


def _reg(*partners):
    return InProcessPartnerRegistry(tuple(partners))


# A realistic stages.gegencheck() shape (any assessed verdict — the ranking precondition (L6,
# P0-C) only cares that ONE ran, not its outcome). Used by the tests below that exercise the
# ranking/pool-lookup logic itself, not the new verdict precondition.
_VERDICT = {"disqualified": False, "basis": "matrix_compatible"}


def test_shipped_capability_seed_is_empty():
    assert (
        len(load_hersteller().faehigkeiten) == 0
    )  # owner-provided, not model-generated


def test_capability_seed_neutrality_keystone_rejects_payment_field():
    # The §3.9 structural guard on the capability SEED lane is UNTOUCHED by the partner model.
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


def test_stage_empty_registry_no_data_zero_firm_names():
    # P1.7 — empty pool (eval/CI): grounded_data=False AND zero firm names; the backend invents none.
    v = stages.alternativen(
        InProcessPartnerRegistry(),
        "Wer kann einen RWDR aus FKM herstellen? Nenne vergleichbare Hersteller.",
        _VERDICT,
        tenant_id="t1",
    )
    assert v is not None and v["grounded_data"] is False
    assert v.get("hersteller", []) == [] and "ordered_by" not in v


def test_stage_none_without_alternatives_keyword():
    assert (
        stages.alternativen(
            _reg(_partner("A")), "Was kann FKM?", _VERDICT, tenant_id="t1"
        )
        is None
    )


def test_stage_none_without_verdict_asks_for_assessment_first():
    # L6 "Matching folgt dem Verdikt, nie umgekehrt" (Relay-Increment P0-C, owner Leitbild-Audit
    # 2026-07-02): the keyword gate alone used to be sufficient. A first-turn manufacturer
    # question with no prior Gegencheck verdict must NOT rank partners — it must ask for the
    # missing assessment instead, with zero firm names (same P1.7 discipline as the empty pool).
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    v = stages.alternativen(
        reg, "Welcher Hersteller kann NBR-RWDR liefern?", None, tenant_id="t1"
    )
    assert v is not None and v["grounded_data"] is False
    assert v.get("hersteller", []) == [] and "ordered_by" not in v
    assert "Bewertung" in v["hinweis"] or "Situationsbewertung" in v["hinweis"]


def test_stage_returns_partner_pool_fit_ranked_and_transparent():
    reg = _reg(
        _partner(
            "Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",), plan="basic"
        ),  # fit 4
        _partner(
            "Premium-Teilfit", werkstoffe=("FKM",), plan="enterprise-xxl"
        ),  # fit 2
    )
    v = stages.alternativen(reg, "Wer macht RWDR aus FKM?", _VERDICT, tenant_id="t1")
    assert (
        v["grounded_data"] is True and v["partner"] is True
    )  # transparent partner pool
    assert [h["firmenname"] for h in v["hersteller"]] == [
        "Voll-Fit",
        "Premium-Teilfit",
    ]  # fit, NOT plan
    assert v["ordered_by"] == "capability"
    assert (
        "lead_email" not in v["hersteller"][0]
    )  # internal routing field NEVER exposed


def test_stage_inactive_partner_not_in_pool():
    v = stages.alternativen(
        _reg(
            _partner("Inaktiv", werkstoffe=("FKM",), bauformen=("RWDR",), aktiv=False)
        ),
        "Wer macht RWDR aus FKM?",
        _VERDICT,
        tenant_id="t1",
    )
    assert v["grounded_data"] is False  # inactive → not a partner → no firm shown


def _pipeline(client, registry, *, matrix=None):
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        partner_registry=registry,
        matrix=matrix,
    )


def test_alternativen_flows_to_result_empty_honest():
    res = asyncio.run(
        _pipeline(FakeLlmClient("Antwort"), InProcessPartnerRegistry()).run(
            "Wer kann das noch herstellen, RWDR aus FKM?", tenant=TenantContext("t1")
        )
    )
    assert res.alternativen is not None and res.alternativen["grounded_data"] is False


def test_alternativen_asks_for_assessment_first_without_verdict_end_to_end():
    # L6 (Relay-Increment P0-C), full pipeline: a manufacturer question with NO recognisable
    # material/medium in it never reaches a Gegencheck verdict (stages.gegencheck requires
    # both) — even with a matching partner in a wired registry, ranking must not fire.
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    res = asyncio.run(
        _pipeline(
            FakeLlmClient("Antwort"), reg, matrix=InProcessCompatibilityMatrix()
        ).run("Welcher Hersteller kann das liefern?", tenant=TenantContext("t1"))
    )
    assert res.gegencheck is None  # no material/medium in the question → no verdict
    assert res.alternativen is not None
    assert res.alternativen["grounded_data"] is False
    assert res.alternativen.get("hersteller", []) == []


def test_alternativen_ranks_once_a_verdict_exists_end_to_end():
    # L6 (Relay-Increment P0-C), full pipeline, positive/regression path: once material+medium
    # are stated (so stages.gegencheck runs — ANY verdict, even a disqualifying one, per the
    # existing FKM+Heißdampf incompatibility fixture in test_gegencheck_pipeline.py), a
    # manufacturer question in the SAME turn ranks partners exactly as before this fix.
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    res = asyncio.run(
        _pipeline(
            FakeLlmClient("Antwort"), reg, matrix=InProcessCompatibilityMatrix()
        ).run(
            "Wir verwenden FKM in Heißdampf, welcher Hersteller kann das liefern?",
            tenant=TenantContext("t1"),
        )
    )
    assert res.gegencheck is not None  # verdict ran (disqualified — irrelevant to matching)
    assert res.alternativen is not None
    assert res.alternativen["grounded_data"] is True
    assert [h["firmenname"] for h in res.alternativen["hersteller"]] == ["Voll-Fit"]


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
