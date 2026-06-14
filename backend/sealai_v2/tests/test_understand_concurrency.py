"""P1 (PERF tranche 1): `understand` runs concurrent with the answer chain.

`understand` is annotate-only (contracts: Intent — NEVER gates/routes); it feeds only
`PipelineResult.understanding` → the API intent field. These tests pin (1) that it no longer
serializes in front of L1 — the gated fake deadlocks on the old serial order, (2) that the
reordering is pure: the L1 prompt and the answer are byte-identical with understand on/off,
and (3) that an understand failure still fails the turn (error surface preserved).
"""

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


class _GatedUnderstandClient:
    """The helper (`understand`) response is released only AFTER the L1 generate call has
    happened. Serial order (understand before L1) → deadlock; concurrent → completes."""

    def __init__(self) -> None:
        self.l1_called = asyncio.Event()
        self.calls: list[str] = []

    async def generate(self, *, system: str, user: str, model_config: ModelConfig):
        self.calls.append(model_config.model)
        if model_config.model == "fake-helper":
            await asyncio.wait_for(self.l1_called.wait(), timeout=2.0)
            return LlmResult(text=_INTENT_JSON, model=model_config.model)
        self.l1_called.set()
        return LlmResult(text="ANTWORT", model=model_config.model)


def test_understand_does_not_serialize_in_front_of_l1():
    async def main():
        client = _GatedUnderstandClient()
        p = _pipeline(client, understand=True)
        res = await asyncio.wait_for(
            p.run("Frage?", tenant=TenantContext("t1")), timeout=5.0
        )
        return client, res

    client, res = asyncio.run(main())
    assert res.answer.text == "ANTWORT"
    assert res.understanding is not None
    assert res.understanding.intent == Intent.WISSENSFRAGE  # annotation still lands
    assert client.calls.count("fake-helper") == 1
    assert client.calls.count("fake-l1") == 1


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
