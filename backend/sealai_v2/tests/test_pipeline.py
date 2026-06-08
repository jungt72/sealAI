from __future__ import annotations

import asyncio

import pytest

from sealai_v2.core.contracts import Flags, Intent, ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext, TenantScopeError
from sealai_v2.tests._fakes import FakeLlmClient


def _pipeline(fake: FakeLlmClient, *, understand: bool = False) -> Pipeline:
    gen = L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1"))
    return Pipeline(
        generator=gen,
        client=fake,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=understand,
    )


def test_answer_returns_canned_and_threads_tenant():
    fake = FakeLlmClient("ANSWER-XYZ")
    res = asyncio.run(
        _pipeline(fake).run(
            "Frage?", tenant=TenantContext("t1"), flags=Flags(False, False)
        )
    )
    assert res.answer.text == "ANSWER-XYZ"
    assert res.tenant_id == "t1"
    assert res.grounded is False and res.verified is False and res.cited is False
    # flags-off → the L1 call's system prompt took the grounding else-branch
    assert "Allgemeinwissen" in fake.calls[-1]["system"]
    assert fake.calls[-1]["user"] == "Frage?"


def test_flags_on_reach_the_prompt():
    fake = FakeLlmClient("A")
    asyncio.run(
        _pipeline(fake).run(
            "Frage?", tenant=TenantContext("t1"), flags=Flags(True, True)
        )
    )
    assert "Sicherheitskritischer Kontext" in fake.calls[-1]["system"]


def test_tenant_is_mandatory_p0():
    fake = FakeLlmClient("A")
    for bad in ("", "   "):
        with pytest.raises(TenantScopeError):
            asyncio.run(_pipeline(fake).run("Frage?", tenant=TenantContext(bad)))


def test_soft_understand_annotates_without_gating():
    fake = FakeLlmClient('{"intent": "fallarbeit", "rationale": "konkrete Situation"}')
    res = asyncio.run(
        _pipeline(fake, understand=True).run(
            "Welche Dichtung?", tenant=TenantContext("t1"), flags=Flags()
        )
    )
    assert res.understanding is not None
    assert res.understanding.intent == Intent.FALLARBEIT
    # the answer is still produced regardless of intent (no gating)
    assert res.answer.text
