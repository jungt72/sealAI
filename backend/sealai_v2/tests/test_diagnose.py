"""Diagnose operation (Modus D) — stage + pipeline + serializer. Offline, no LLM.

The diagnose stage returns cause/fix only from a reviewed failure-mode entry. Draft entries are
quarantined at the serve boundary; the seed is all-draft today.
"""

from __future__ import annotations

import asyncio

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, ModelConfig, PipelineResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.versagensmodi import (
    InProcessVersagensmodiStore,
    VersagensmodiCatalog,
    _mode,
)
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def _store():
    return InProcessVersagensmodiStore()


# --- stage ---------------------------------------------------------------


def test_stage_draft_match_is_quarantined_without_cause_fix():
    v = stages.diagnose(
        _store(),
        "Meine NBR-Dichtlippe ist hart und rissig geworden und leckt jetzt",
        tenant_id="t1",
    )
    assert v is not None
    assert v["provisional"] is True
    assert v["quarantined"] is True
    assert "ursache" not in v and "fix" not in v and "source" not in v


def test_stage_matches_swelling():
    v = stages.diagnose(
        _store(), "die Dichtung quillt auf und wird weich in Mineralöl", tenant_id="t1"
    )
    assert v is not None
    assert v["quarantined"] is True


def test_stage_reviewed_match_may_return_cause_and_fix():
    reviewed = _mode(
        {
            "id": "VM-REVIEWED-TEST",
            "symptom": "Rissige Dichtlippe",
            "ursache": "Owner-geprüfte Ursache",
            "fix": "Owner-geprüfter Prüfpfad",
            "betrifft_archetypen": ["RWDR"],
            "review_state": "reviewed",
            "scope": {"symptom": ["rissig"], "material": ["NBR"]},
            "provenance": ["owner:diagnose-review"],
            "sources": [],
        }
    )
    store = InProcessVersagensmodiStore(
        VersagensmodiCatalog(modes=(reviewed,), version="test", source="owner")
    )
    out = stages.diagnose(store, "NBR ist rissig", tenant_id="t1")
    assert out is not None
    assert out["provisional"] is False and out["quarantined"] is False
    assert out["ursache"] == "Owner-geprüfte Ursache"
    assert out["fix"] == "Owner-geprüfter Prüfpfad"


def test_stronger_draft_match_is_quarantined_instead_of_using_weaker_reviewed_mode():
    draft = _mode(
        {
            "id": "VM-DRAFT-EXACT",
            "symptom": "Rissige Dichtlippe in Mineralöl",
            "ursache": "Ungeprüfte spezifische Ursache",
            "fix": "Ungeprüfte spezifische Maßnahme",
            "betrifft_archetypen": ["RWDR"],
            "review_state": "draft",
            "scope": {
                "symptom": ["rissig"],
                "material": ["NBR"],
                "medium": ["mineralöl"],
            },
            "provenance": ["draft:test"],
        }
    )
    reviewed = _mode(
        {
            "id": "VM-REVIEWED-WEAKER",
            "symptom": "Rissige Dichtlippe",
            "ursache": "Geprüfte, aber schwächere Ursache",
            "fix": "Geprüfter, aber schwächerer Prüfpfad",
            "betrifft_archetypen": ["RWDR"],
            "review_state": "reviewed",
            "scope": {"symptom": ["rissig"], "material": ["NBR"]},
            "provenance": ["owner:diagnose-review"],
        }
    )
    store = InProcessVersagensmodiStore(
        VersagensmodiCatalog(modes=(draft, reviewed), version="test", source="owner")
    )
    out = stages.diagnose(store, "NBR ist in Mineralöl rissig", tenant_id="t1")
    assert out is not None and out["quarantined"] is True
    assert "ursache" not in out and "fix" not in out


def test_stage_none_without_symptom():
    assert (
        stages.diagnose(_store(), "Welche Dichtung für mein Getriebe?", tenant_id="t1")
        is None
    )


def test_stage_none_when_store_off():
    assert stages.diagnose(None, "die Lippe ist rissig", tenant_id="t1") is None


# --- pipeline end-to-end -------------------------------------------------


def _pipeline(client, *, with_store=True):
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        versagensmodi=InProcessVersagensmodiStore() if with_store else None,
    )


def _run(p, q):
    return asyncio.run(p.run(q, tenant=TenantContext("t1")))


def test_diagnosis_flows_to_result():
    res = _run(
        _pipeline(FakeLlmClient("Antwort")),
        "mein Wellendichtring leckt, die Lippe ist hart und rissig",
    )
    assert res.diagnose is not None
    assert res.diagnose["quarantined"] is True
    assert "ursache" not in res.diagnose and "fix" not in res.diagnose


def test_no_diagnosis_on_non_symptom_turn():
    res = _run(_pipeline(FakeLlmClient("Antwort")), "Was kann FKM?")
    assert res.diagnose is None


def test_failure_mode_vocabulary_in_knowledge_overview_is_not_a_diagnosis():
    res = _run(
        _pipeline(FakeLlmClient("Antwort")),
        (
            "Erkläre die technische Auslegung eines O-Rings: Verpressung, "
            "Extrusionsspalt und Versagensbilder."
        ),
    )
    assert res.diagnose is None


def test_failure_mode_axes_in_material_comparison_are_not_a_diagnosis():
    res = _run(
        _pipeline(FakeLlmClient("Antwort")),
        (
            "Vergleiche NBR und PTFE als Dichtungswerkstoffe: Rückstellung/Kriechen, "
            "Reibung/Verschleiß, Grenzen und Versagensmechanismen."
        ),
    )
    assert res.diagnose is None


def test_no_diagnosis_when_store_off():
    res = _run(
        _pipeline(FakeLlmClient("Antwort"), with_store=False),
        "die Lippe ist rissig und leckt",
    )
    assert res.diagnose is None


# --- serializer ----------------------------------------------------------


def test_serializer_surfaces_diagnose():
    out = chat_response(
        PipelineResult(
            question="leckt",
            tenant_id="t1",
            flags=Flags(),
            understanding=None,
            answer=Answer(text="…", model="fake"),
            diagnose={"ursache": "x", "fix": "y", "source": "z", "provisional": True},
        )
    )
    assert out["diagnose"]["provisional"] is True
    assert out["diagnose"]["quarantined"] is True
    assert "ursache" not in out["diagnose"] and "fix" not in out["diagnose"]
    out_none = chat_response(
        PipelineResult(
            question="x",
            tenant_id="t1",
            flags=Flags(),
            understanding=None,
            answer=Answer(text="…", model="fake"),
        )
    )
    assert out_none["diagnose"] is None
