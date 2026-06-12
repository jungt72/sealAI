"""P4a — the optional progress sink on ``pipeline.run`` (SSE stage-progress, zero LLM calls).

Pins: (1) the chain emits (stage, start/end) at every existing P0 seam in order; (2) the
default ``progress=None`` keeps the turn byte-identical to today; (3) a raising sink can
never alter or fail a turn; (4) events carry stage keys only — ``understand`` is concurrent
(P1) so it is asserted present + paired, never position-fixed.
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient

_T = TenantContext("tenant-prog")
_CLEAN = json.dumps({"findings": [], "verdict": "clean"})

# The answer chain in pipeline order. `understand` (concurrent, P1) is checked separately.
_CHAIN = ["recall", "ground", "compute", "generate", "verify", "cite"]


def _pipeline(client, *, understand: bool = False, verify: bool = True) -> Pipeline:
    cat = load_traps() if verify else None
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=understand,
        verifier=(
            L3Verifier(client, VerifierPromptAssembler(), ModelConfig("fake-l3"), cat)
            if verify
            else None
        ),
        catalog=cat,
        retriever=InProcessRetriever(),
    )


def test_progress_emits_every_chain_seam_in_order_with_paired_start_end():
    events: list[tuple[str, str]] = []
    client = ScriptedFakeLlmClient(["Antwort.", _CLEAN])
    asyncio.run(
        _pipeline(client).run(
            "Welche Frage?", tenant=_T, progress=lambda s, st: events.append((s, st))
        )
    )
    chain = [e for e in events if e[0] in _CHAIN]
    expected = [(s, st) for s in _CHAIN for st in ("start", "end")]
    assert chain == expected


def test_understand_events_are_present_and_paired_when_enabled():
    events: list[tuple[str, str]] = []
    client = FakeLlmClient("Antwort.")  # parse-tolerant understand → Intent.UNKLAR
    asyncio.run(
        _pipeline(client, understand=True, verify=False).run(
            "Frage?", tenant=_T, progress=lambda s, st: events.append((s, st))
        )
    )
    understand = [st for s, st in events if s == "understand"]
    assert understand == ["start", "end"]


def test_default_progress_none_keeps_the_answer_byte_identical():
    with_sink = asyncio.run(
        _pipeline(ScriptedFakeLlmClient(["Antwort.", _CLEAN])).run(
            "Frage?", tenant=_T, progress=lambda s, st: None
        )
    )
    without = asyncio.run(
        _pipeline(ScriptedFakeLlmClient(["Antwort.", _CLEAN])).run("Frage?", tenant=_T)
    )
    assert with_sink.answer.text == without.answer.text
    assert with_sink.grounded == without.grounded
    assert with_sink.verified == without.verified


def test_a_raising_sink_never_fails_or_alters_the_turn():
    def bomb(stage: str, status: str) -> None:
        raise RuntimeError("sink boom")

    res = asyncio.run(
        _pipeline(ScriptedFakeLlmClient(["Antwort.", _CLEAN])).run(
            "Frage?", tenant=_T, progress=bomb
        )
    )
    assert res.answer.text == "Antwort."
    assert res.verified is True


def test_failure_mid_generate_leaves_no_end_for_that_stage():
    class _Boom(FakeLlmClient):
        async def generate(self, *, system, user, model_config):
            raise RuntimeError("llm down")

    events: list[tuple[str, str]] = []
    try:
        asyncio.run(
            _pipeline(_Boom(), verify=False).run(
                "Frage?", tenant=_T, progress=lambda s, st: events.append((s, st))
            )
        )
    except RuntimeError:
        pass
    else:  # pragma: no cover - the run must fail
        raise AssertionError("expected the turn to fail")
    assert ("generate", "start") in events
    assert ("generate", "end") not in events  # no synthetic end on failure
