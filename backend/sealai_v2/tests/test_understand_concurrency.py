"""P1 (PERF) + G4 (V2.1 Inc 1): `understand` runs concurrent with ground+compute, then is awaited
BEFORE generate.

`understand` is annotate-only (contracts: Intent/archetype — NEVER gates/routes); it feeds
`PipelineResult.understanding` AND (G4) the soft archetype that injects the matching profile's
advisory context into the L1 prompt. Because the archetype must be in the prompt, understand is now
awaited before generate (it still overlaps ground+compute — the P1 'never serialize in front of L1'
contract is intentionally superseded by the archetype-in-prompt requirement; owner-accepted, ONE
helper call, latency measured). These tests pin (1) understand COMPLETES before the L1 call, (2) the
no-archetype path is pure: the L1 prompt + answer are byte-identical with understand on/off, and
(3) an understand failure still fails the turn (error surface preserved)."""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.core.contracts import Intent, LlmResult, ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient

_INTENT_JSON = '{"intent": "wissensfrage", "rationale": "kurz"}'


def _pipeline(client, *, understand: bool) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=understand,
    )


def test_understand_completes_before_l1_generate():
    """G4 ordering: understand is awaited BEFORE generate (so a recognised archetype can guide the L1
    prompt). It still overlaps ground+compute, but the helper call now completes before the L1 call.
    Replaces the P1 'understand does not serialize in front of L1' contract — superseded by the
    archetype-in-prompt requirement (owner-accepted; still ONE helper call)."""
    fake = FakeLlmClient(_INTENT_JSON)  # same text serves understand (parsed) AND L1
    res = asyncio.run(
        _pipeline(fake, understand=True).run("Frage?", tenant=TenantContext("t1"))
    )
    assert res.understanding is not None
    assert res.understanding.intent == Intent.WISSENSFRAGE  # annotation still lands
    helper_idx = next(i for i, c in enumerate(fake.calls) if c["model"] == "fake-helper")
    l1_idx = next(i for i, c in enumerate(fake.calls) if c["model"] == "fake-l1")
    assert helper_idx < l1_idx  # understand completed before the L1 generate (the new ordering)
    assert sum(c["model"] == "fake-helper" for c in fake.calls) == 1  # exactly one helper call


def test_reordering_is_pure_l1_prompt_and_answer_byte_identical():
    fake_on = FakeLlmClient(_INTENT_JSON)  # same text serves understand AND L1 (fake)
    asyncio.run(
        _pipeline(fake_on, understand=True).run("Frage?", tenant=TenantContext("t1"))
    )
    fake_off = FakeLlmClient(_INTENT_JSON)
    asyncio.run(
        _pipeline(fake_off, understand=False).run("Frage?", tenant=TenantContext("t1"))
    )

    (l1_on,) = [c for c in fake_on.calls if c["model"] == "fake-l1"]
    (l1_off,) = [c for c in fake_off.calls if c["model"] == "fake-l1"]
    assert l1_on["system"] == l1_off["system"]
    assert l1_on["user"] == l1_off["user"] == "Frage?"


class _FailingUnderstandClient:
    async def generate(self, *, system: str, user: str, model_config: ModelConfig):
        if model_config.model == "fake-helper":
            raise RuntimeError("understand-boom")
        return LlmResult(text="ANTWORT", model=model_config.model)


def test_understand_failure_still_fails_the_turn():
    p = _pipeline(_FailingUnderstandClient(), understand=True)
    with pytest.raises(RuntimeError, match="understand-boom"):
        asyncio.run(p.run("Frage?", tenant=TenantContext("t1")))
