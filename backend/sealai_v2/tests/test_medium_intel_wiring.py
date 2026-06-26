"""Wiring: Medium Intelligence (Phase 2) flows to the PipelineResult + the chat serializer ONLY when
the flag is on, and is OFF by default (→ None, L1-neutral). Mirrors the Modus-F wiring test."""

from __future__ import annotations

import asyncio

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, ModelConfig, PipelineResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.medium_research import MediumIntelligence, MediumResearcher
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import MediumResearchPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient

_GOOD = (
    '{"eigenschaften":["unpolar, ölbasiert"],"herausforderungen":["Quellung von EPDM"],'
    '"werkstoff_tendenz":["eher NBR/FKM"],"unsicher":false}'
)


def _pipeline(*, enabled: bool):
    client = FakeLlmClient("Antwort")
    researcher = MediumResearcher(
        FakeLlmClient(_GOOD), MediumResearchPromptAssembler(), ModelConfig("fake-h")
    )
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        medium_researcher=researcher,
        medium_intel_enabled=enabled,
    )


def test_medium_intel_flows_to_result_when_enabled():
    res = asyncio.run(
        _pipeline(enabled=True).run(
            "Ich brauche eine Dichtung für Hydrauliköl", tenant=TenantContext("t1")
        )
    )
    mi = res.medium_intelligence
    assert mi is not None and "unpolar, ölbasiert" in mi.eigenschaften
    assert mi.medium == "Hydrauliköl"  # deterministic extract from the current message


def test_medium_intel_off_by_default_is_none():
    res = asyncio.run(
        _pipeline(enabled=False).run(
            "Dichtung für Hydrauliköl", tenant=TenantContext("t1")
        )
    )
    assert res.medium_intelligence is None  # L1-neutral default


def test_serializer_surfaces_when_present_and_omits_when_absent():
    base = dict(
        question="x",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
    )
    out = chat_response(
        PipelineResult(
            **base,
            medium_intelligence=MediumIntelligence(
                "Salzsäure", "Sonstiges", eigenschaften=("stark sauer",)
            ),
        )
    )
    assert out["medium_intelligence"]["medium"] == "Salzsäure"
    assert out["medium_intelligence"]["vorlaeufig"] is True
    assert chat_response(PipelineResult(**base))["medium_intelligence"] is None
