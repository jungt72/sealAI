"""Pipeline wiring of Legal-by-Design Phase D risk flags: detection is ALWAYS on and always
attached to PipelineResult; reaching the L1 prompt is gated behind risk_flag_prompt_enabled
(default OFF -> byte-identical prompt even when risk_flags matched)."""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import Flags, ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def _pipeline(
    fake: FakeLlmClient, *, risk_flag_prompt_enabled: bool = False
) -> Pipeline:
    gen = L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1"))
    return Pipeline(
        generator=gen,
        client=fake,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        risk_flag_prompt_enabled=risk_flag_prompt_enabled,
    )


def test_risk_flags_always_populated_regardless_of_the_prompt_flag():
    fake = FakeLlmClient("ok")
    res = asyncio.run(
        _pipeline(fake, risk_flag_prompt_enabled=False).run(
            "Ist FKM für ATEX-Zonen geeignet?",
            tenant=TenantContext("t1"),
            flags=Flags(False, False),
        )
    )
    assert res.risk_flags == ("ATEX",)


def test_no_match_yields_empty_risk_flags():
    fake = FakeLlmClient("ok")
    res = asyncio.run(
        _pipeline(fake).run(
            "Welches Material für Hydrauliköl bei 80°C?",
            tenant=TenantContext("t1"),
            flags=Flags(False, False),
        )
    )
    assert res.risk_flags == ()


def test_prompt_flag_off_keeps_risk_flags_out_of_the_l1_prompt():
    fake = FakeLlmClient("ok")
    asyncio.run(
        _pipeline(fake, risk_flag_prompt_enabled=False).run(
            "Ist FKM für ATEX-Zonen geeignet?",
            tenant=TenantContext("t1"),
            flags=Flags(False, False),
        )
    )
    assert (
        "Regulierter/sicherheitskritischer Anwendungsbereich erkannt"
        not in fake.calls[-1]["system"]
    )


def test_prompt_flag_on_injects_risk_flags_into_the_l1_prompt():
    fake = FakeLlmClient("ok")
    asyncio.run(
        _pipeline(fake, risk_flag_prompt_enabled=True).run(
            "Ist FKM für ATEX-Zonen geeignet?",
            tenant=TenantContext("t1"),
            flags=Flags(False, False),
        )
    )
    system = fake.calls[-1]["system"]
    assert (
        "Regulierter/sicherheitskritischer Anwendungsbereich erkannt (ATEX)" in system
    )


def test_prompt_flag_on_but_no_match_still_omits_the_block():
    fake = FakeLlmClient("ok")
    asyncio.run(
        _pipeline(fake, risk_flag_prompt_enabled=True).run(
            "Welches Material für Hydrauliköl bei 80°C?",
            tenant=TenantContext("t1"),
            flags=Flags(False, False),
        )
    )
    assert (
        "Regulierter/sicherheitskritischer Anwendungsbereich erkannt"
        not in fake.calls[-1]["system"]
    )
