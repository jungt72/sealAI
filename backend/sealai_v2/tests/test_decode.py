"""Decode operation (Modus G) — stage + pipeline + serializer. Offline, no LLM.

Fires only on a designation with a dimension group; result-side structured parse + the §9.2
equivalence boundary (never an X=Y claim).
"""

from __future__ import annotations

import asyncio

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, ModelConfig, PipelineResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def test_stage_decodes_rwdr():
    v = stages.decode("Schlüssel mir RWDR 40x62x10 FKM auf")
    assert v is not None
    assert v["type"] == "RWDR" and v["material"] == "FKM"
    assert (v["id_mm"], v["od_mm"], v["width_mm"]) == (40.0, 62.0, 10.0)


def test_stage_carries_equivalence_boundary():
    v = stages.decode("BAUMSL 40-62-10 FKM")
    assert "keine Austausch-Garantie" in v["equivalenz_grenze"]


def test_stage_none_without_dimension_group():
    assert (
        stages.decode("eine FKM-Dichtung, was kann die?") is None
    )  # material, no dims
    assert stages.decode("Welche Dichtung empfehlen Sie?") is None


def _pipeline(client):
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
    )


def _run(p, q):
    return asyncio.run(p.run(q, tenant=TenantContext("t1")))


def test_decode_flows_to_result():
    res = _run(
        _pipeline(FakeLlmClient("Antwort")),
        "Schlüssel BAUMSL 40-62-10 FKM auf und finde Vergleichbares",
    )
    assert res.decode is not None
    assert res.decode["id_mm"] == 40.0
    assert "Hersteller" in res.decode["equivalenz_grenze"]


def test_no_decode_on_non_designation_turn():
    res = _run(_pipeline(FakeLlmClient("Antwort")), "Was kann FKM?")
    assert res.decode is None


def test_serializer_surfaces_decode():
    out = chat_response(
        PipelineResult(
            question="x",
            tenant_id="t1",
            flags=Flags(),
            understanding=None,
            answer=Answer(text="…", model="fake"),
            decode={"raw": "40x62x10", "id_mm": 40.0, "equivalenz_grenze": "…"},
        )
    )
    assert out["decode"]["id_mm"] == 40.0
