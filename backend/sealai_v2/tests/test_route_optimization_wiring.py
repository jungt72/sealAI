"""Phase 2B (LangGraph-suitability audit) — end-to-end wiring tests for the route-optimization
flag in Pipeline.run(). Verifies real behavior, not just the classifier in isolation:

1. Flag OFF (default): behavior is unchanged for both a smalltalk turn and an engineering turn —
   the L3 verifier always runs when wired (today's behavior).
2. Flag ON + a genuine smalltalk turn (zero deterministic engineering signals): the LLM-based L3
   verifier is skipped; the EXISTING run_parametric_guard fallback still runs (no new/weaker guard).
3. Flag ON + an engineering turn (a deterministic signal is present): the LLM-based L3 verifier
   still runs — completely unaffected by the flag. This is the core safety invariant end-to-end.
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import Flags, LlmResult, ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.pipeline.route_telemetry import RouteTelemetry
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.security.tenant import TenantContext

_T = TenantContext("route-wiring-tenant")
_CLEAN_VERDICT = json.dumps({"findings": [], "verdict": "clean"})
_SMALLTALK_INTENT = json.dumps({"intent": "gespraech", "rationale": "Begruessung"})


class _StageRoutingFakeClient:
    """Routes purely by ``model_config.stage`` (the Phase-1 telemetry field) — no fragile prompt-
    text matching. Records every call's stage for assertions."""

    def __init__(self, *, understand_json: str, l1_answer: str) -> None:
        self._understand_json = understand_json
        self._l1_answer = l1_answer
        self.calls: list[str] = []

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        stage = model_config.stage or "unknown"
        self.calls.append(stage)
        if stage == "understand":
            return LlmResult(
                text=self._understand_json,
                model=model_config.model,
                finish_reason="stop",
            )
        if stage == "verifier":
            return LlmResult(
                text=_CLEAN_VERDICT, model=model_config.model, finish_reason="stop"
            )
        return LlmResult(
            text=self._l1_answer, model=model_config.model, finish_reason="stop"
        )


class _SpyRouteSink:
    def __init__(self) -> None:
        self.events: list[RouteTelemetry] = []

    def record(self, event: RouteTelemetry) -> None:
        self.events.append(event)


def _pipeline(client, *, route_optimization_enabled: bool, sink=None) -> Pipeline:
    cat = load_traps()
    gen = L1Generator(client, PromptAssembler(), ModelConfig("fake-l1", stage="l1"))
    verifier = L3Verifier(
        client, VerifierPromptAssembler(), ModelConfig("fake-l3", stage="verifier"), cat
    )
    return Pipeline(
        generator=gen,
        client=client,
        helper_model=ModelConfig("fake-helper", stage="understand"),
        understand_enabled=True,
        verifier=verifier,
        catalog=cat,
        route_optimization_enabled=route_optimization_enabled,
        route_telemetry_sink=sink,
    )


def test_flag_off_smalltalk_still_runs_full_l3() -> None:
    """Byte-identical-to-today check: with the flag OFF, even an obvious smalltalk turn keeps
    running the LLM-based L3 verifier exactly as before Phase 2B."""
    client = _StageRoutingFakeClient(
        understand_json=_SMALLTALK_INTENT, l1_answer="Hallo!"
    )
    p = _pipeline(client, route_optimization_enabled=False)
    asyncio.run(p.run("Hallo, wie geht's dir?", tenant=_T, flags=Flags()))
    assert client.calls.count("verifier") == 1


def test_flag_on_engineering_case_still_runs_full_l3() -> None:
    """The core safety invariant, end to end: a real engineering question with a deterministic
    signal (a dimension) MUST still run the full L3 verifier even with the flag ON."""
    client = _StageRoutingFakeClient(
        understand_json=json.dumps({"intent": "fallarbeit", "rationale": "Fall"}),
        l1_answer="Antwort zum Fall.",
    )
    p = _pipeline(client, route_optimization_enabled=True)
    asyncio.run(
        p.run(
            "RWDR 45x62x8, welches Material bei Hydrauliköl?", tenant=_T, flags=Flags()
        )
    )
    assert client.calls.count("verifier") == 1


def test_flag_on_genuine_smalltalk_skips_llm_verifier() -> None:
    """The actual win: flag ON + zero engineering signals + a gespraech intent -> the LLM-based
    verifier is skipped. The turn must still complete successfully (via run_parametric_guard)."""
    client = _StageRoutingFakeClient(
        understand_json=_SMALLTALK_INTENT, l1_answer="Hallo!"
    )
    p = _pipeline(client, route_optimization_enabled=True)
    result = asyncio.run(p.run("Hallo, wie geht's dir?", tenant=_T, flags=Flags()))
    assert client.calls.count("verifier") == 0
    assert (
        result.answer.text
    )  # the turn still produced an answer via the deterministic fallback


def test_flag_on_emits_route_telemetry_with_safe_fields_only() -> None:
    client = _StageRoutingFakeClient(
        understand_json=_SMALLTALK_INTENT, l1_answer="Hallo!"
    )
    sink = _SpyRouteSink()
    p = _pipeline(client, route_optimization_enabled=True, sink=sink)
    asyncio.run(p.run("Hallo, wie geht's dir?", tenant=_T, flags=Flags()))

    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.route_name == "smalltalk_navigation"
    assert ev.forced_full_pipeline is False
    assert ev.deterministic_signal_count == 0
    assert ev.route_latency_ms >= 0
    # No raw content anywhere on the telemetry event.
    dumped = repr(ev)
    assert "Hallo, wie geht's dir?" not in dumped


def test_flag_on_but_no_sink_wired_is_fully_inert() -> None:
    """route_telemetry_sink defaults to None even when the flag is ON — must not raise."""
    client = _StageRoutingFakeClient(
        understand_json=_SMALLTALK_INTENT, l1_answer="Hallo!"
    )
    p = _pipeline(client, route_optimization_enabled=True, sink=None)
    result = asyncio.run(p.run("Hallo, wie geht's dir?", tenant=_T, flags=Flags()))
    assert result.answer.text


class _RaisingRouteSink:
    def record(self, event: RouteTelemetry) -> None:
        raise RuntimeError("sink boom")


def test_a_raising_route_sink_never_breaks_the_turn() -> None:
    client = _StageRoutingFakeClient(
        understand_json=_SMALLTALK_INTENT, l1_answer="Hallo!"
    )
    p = _pipeline(client, route_optimization_enabled=True, sink=_RaisingRouteSink())
    result = asyncio.run(p.run("Hallo, wie geht's dir?", tenant=_T, flags=Flags()))
    assert result.answer.text


def test_knowledge_route_never_skips_l3_even_with_zero_signals() -> None:
    """Safety correction proof: a stress test against the real eval seed cases found phrasings
    where general_sealing_knowledge/material_knowledge's deterministic signals under-fire (natural-
    language variety no finite keyword list fully covers). Rather than chase that, the ACTUAL
    L3-bypass is restricted to smalltalk_navigation only — general_sealing_knowledge/
    material_knowledge are labeled for telemetry but must NEVER skip the LLM verifier. This test
    picks a question that WOULD be classified general_sealing_knowledge (zero Stage-1 signals +
    intent=wissensfrage) and proves the verifier still runs regardless."""
    client = _StageRoutingFakeClient(
        understand_json=json.dumps(
            {"intent": "wissensfrage", "rationale": "Wissensfrage"}
        ),
        l1_answer="Eine Erklaerung.",
    )
    p = _pipeline(client, route_optimization_enabled=True)
    asyncio.run(p.run("Was ist eine Dichtung allgemein?", tenant=_T, flags=Flags()))
    assert client.calls.count("verifier") == 1


def test_material_knowledge_route_never_skips_l3_even_with_zero_signals() -> None:
    client = _StageRoutingFakeClient(
        understand_json=json.dumps(
            {"intent": "wissensfrage", "rationale": "Wissensfrage"}
        ),
        l1_answer="Eine Erklaerung.",
    )
    p = _pipeline(client, route_optimization_enabled=True)
    asyncio.run(p.run("Was ist PTFE?", tenant=_T, flags=Flags()))
    assert client.calls.count("verifier") == 1
