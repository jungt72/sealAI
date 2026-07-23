"""INC-CALC-ROUTE-RELEVANCE — end-to-end tests for suppressing the calc-kernel PROMPT context on
non-kernel routes.

Background (real production report): a purely conceptual question ("bitte gebe mir informationen zu
der funktion eines RWDR") classifies as ``general_sealing_knowledge`` (kernel=False), yet the
delivered answer drifted into a confusing "Umfangsgeschwindigkeit: nicht berechenbar — Eingaben
fehlen (d1_mm, rpm)" tangent. Root cause: ``stages.compute`` runs UNCONDITIONALLY for every turn
BEFORE route classification, so a ``calc`` (incl. its ``not_computed`` entries) exists on every
turn, and it was fed into the L1 prompt regardless of route. The LLM noticed the off-topic
``not_computed`` kernel entry and commented on it, which output_guard then had to correct into the
confusing user-facing text. This is NOT a hallucination/safety failure (no fabricated number
reached the user — the guard worked); it is a prompt-relevance quality bug.

The fix (flag ``suppress_calc_for_non_kernel_routes_enabled``): when the flag is on AND route
classification ran AND the classified route's ``route_prompt_matrix`` ``kernel`` flag is False, the
L1 generator's prompt receives an EMPTY ``CalcResult()`` instead of the real ``calc``. NOTHING else
changes — the guard contract, L3 ``verify()`` and the response payload's ``computed``/``not_computed``
fields all still reflect the REAL ``calc``. Default OFF → byte-identical to today.

These tests prove, end to end via ``Pipeline.run()``:
  1. flag ON + a kernel=False route (general_sealing_knowledge / material_knowledge) → the L1
     generator is called with an EMPTY calc regardless of the real computed calc.
  2. flag ON + a kernel=True route (engineering_case) → the L1 generator still gets the REAL calc.
  3. flag OFF (default) → EVERY route gets the real calc (byte-identical hard gate).
  4. the guard contract and L3 verify() receive the same answer-relevant calc as L1, while the
     response payload still reflects the REAL calc as telemetry (explicit assertions, not assumed).
  5. the actual bug repro: general_sealing_knowledge + a real Umfangsgeschwindigkeit ``not_computed``
     entry → L1 gets an empty calc (no basis to comment) while the payload still shows the real
     ``not_computed`` for transparency.
  6. BOTH the non-streaming and the Phase-3B draft-streaming L1 call sites are covered.
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import (
    CalcResult,
    Flags,
    LlmResult,
    LlmStreamEvent,
    ModelConfig,
    NotComputed,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.security.tenant import TenantContext

_T = TenantContext("calc-suppression-tenant")
_CLEAN_VERDICT = json.dumps({"findings": [], "verdict": "clean"})

# A realistic non-empty calc with a kernel-only ``not_computed`` entry — exactly the shape that
# leaked into the RWDR-function answer (Umfangsgeschwindigkeit unresolvable, inputs missing).
_UMFANG_NOT_COMPUTED = NotComputed(
    calc_id="umfangsgeschwindigkeit",
    reason="nicht berechenbar: Eingaben fehlen (d1_mm, rpm)",
)
_SYNTH_CALC = CalcResult(not_computed=(_UMFANG_NOT_COMPUTED,))


def _wissensfrage(rationale: str = "Wissensfrage") -> str:
    return json.dumps({"intent": "wissensfrage", "rationale": rationale})


def _fallarbeit() -> str:
    return json.dumps({"intent": "fallarbeit", "rationale": "Fall"})


class _CalcSpyGenerator(L1Generator):
    """An L1Generator that records the ``calc`` kwarg it receives on EACH ``generate`` /
    ``generate_stream`` call, then delegates VERBATIM to the real implementation (so prompt assembly
    and the returned Answer are unchanged). Lets a test assert exactly what calc context the L1
    PROMPT was built from, for both the non-streaming and the draft-streaming call sites."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[str, CalcResult | None]] = []

    async def generate(self, question: str, **kwargs):
        self.calls.append(("generate", kwargs.get("calc")))
        return await super().generate(question, **kwargs)

    async def generate_stream(self, question: str, **kwargs):
        self.calls.append(("stream", kwargs.get("calc")))
        async for event in super().generate_stream(question, **kwargs):
            yield event

    @property
    def l1_calcs(self) -> list[CalcResult | None]:
        return [calc for _, calc in self.calls]


class _StageRoutingStreamClient:
    """Routes purely by ``model_config.stage``: understand → the supplied intent JSON; verifier →
    a clean verdict; l1 → the fixed answer. Supports BOTH ``generate`` and ``generate_stream`` so
    the same double exercises the non-streaming and the Phase-3B draft-streaming L1 paths."""

    def __init__(
        self, *, understand_json: str, l1_answer: str = "Eine Erklaerung."
    ) -> None:
        self._understand_json = understand_json
        self._l1_answer = l1_answer

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        stage = model_config.stage or "unknown"
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

    async def generate_stream(
        self, *, system: str, user: str, model_config: ModelConfig
    ):
        # Only the L1 stage ever calls generate_stream (understand/verify use generate()).
        yield LlmStreamEvent(delta=self._l1_answer)
        yield LlmStreamEvent(
            result=LlmResult(
                text=self._l1_answer, model=model_config.model, finish_reason="stop"
            )
        )


def _pipeline(
    client,
    *,
    suppress: bool,
    draft_streaming: bool = False,
    with_verifier: bool = False,
) -> tuple[Pipeline, _CalcSpyGenerator]:
    cat = load_traps()
    gen = _CalcSpyGenerator(
        client, PromptAssembler(), ModelConfig("fake-l1", stage="l1")
    )
    verifier = (
        L3Verifier(
            client,
            VerifierPromptAssembler(),
            ModelConfig("fake-l3", stage="verifier"),
            cat,
        )
        if with_verifier
        else None
    )
    pipeline = Pipeline(
        generator=gen,
        client=client,
        helper_model=ModelConfig("fake-helper", stage="understand"),
        understand_enabled=True,
        verifier=verifier,
        catalog=cat if with_verifier else None,
        route_optimization_enabled=True,  # routing MUST run for the fix to have anything to suppress
        suppress_calc_for_non_kernel_routes_enabled=suppress,
        draft_token_streaming_enabled=draft_streaming,
    )
    return pipeline, gen


def _run(pipeline: Pipeline, question: str, *, token_sink=None):
    return asyncio.run(
        pipeline.run(question, tenant=_T, flags=Flags(), token_sink=token_sink)
    )


def _patch_compute(monkeypatch, calc: CalcResult) -> None:
    async def _fake_compute(*_args, **_kwargs):
        return calc

    monkeypatch.setattr(stages, "compute", _fake_compute)


# ── 1 + 5: flag ON + kernel=False route → L1 gets an EMPTY calc; payload keeps the real one --------


def test_flag_on_general_knowledge_l1_receives_empty_calc(monkeypatch) -> None:
    _patch_compute(monkeypatch, _SYNTH_CALC)
    client = _StageRoutingStreamClient(understand_json=_wissensfrage())
    pipeline, gen = _pipeline(client, suppress=True)

    result = _run(pipeline, "Was ist eine Dichtung allgemein?")

    # Guard the premise: the turn really did classify as the kernel=False knowledge route.
    assert result.route_name == "general_sealing_knowledge"
    # The L1 PROMPT was built from an EMPTY calc — no basis to comment on Umfangsgeschwindigkeit.
    assert gen.l1_calcs == [CalcResult()]
    assert gen.l1_calcs[0].computed == ()
    assert gen.l1_calcs[0].not_computed == ()
    # Transparency invariant: the RESPONSE PAYLOAD still reflects the REAL not_computed entry.
    assert result.not_computed == (_UMFANG_NOT_COMPUTED,)


def test_flag_on_material_knowledge_l1_receives_empty_calc(monkeypatch) -> None:
    _patch_compute(monkeypatch, _SYNTH_CALC)
    client = _StageRoutingStreamClient(understand_json=_wissensfrage())
    pipeline, gen = _pipeline(client, suppress=True)

    result = _run(pipeline, "Was ist PTFE?")

    assert result.route_name == "material_knowledge"
    assert gen.l1_calcs == [CalcResult()]
    assert result.not_computed == (_UMFANG_NOT_COMPUTED,)


# ── 2: flag ON + kernel=True route → L1 still gets the REAL calc -----------------------------------


def test_flag_on_engineering_case_l1_receives_real_calc(monkeypatch) -> None:
    _patch_compute(monkeypatch, _SYNTH_CALC)
    client = _StageRoutingStreamClient(understand_json=_fallarbeit())
    pipeline, gen = _pipeline(client, suppress=True)

    result = _run(pipeline, "RWDR 45x62x8, welches Material bei Hydraulikoel?")

    assert result.route_name == "engineering_case"
    # kernel=True route: the L1 prompt is UNCHANGED — it still receives the real, unsuppressed calc.
    assert gen.l1_calcs == [_SYNTH_CALC]
    assert gen.l1_calcs[0].not_computed == (_UMFANG_NOT_COMPUTED,)


# ── 3: flag OFF (default) → EVERY route gets the real calc (byte-identical hard gate) --------------


def test_flag_off_general_knowledge_l1_receives_real_calc(monkeypatch) -> None:
    _patch_compute(monkeypatch, _SYNTH_CALC)
    client = _StageRoutingStreamClient(understand_json=_wissensfrage())
    pipeline, gen = _pipeline(client, suppress=False)

    result = _run(pipeline, "Was ist eine Dichtung allgemein?")

    assert result.route_name == "general_sealing_knowledge"
    # Flag OFF: even a kernel=False route gets the real calc — byte-identical to pre-fix behavior.
    assert gen.l1_calcs == [_SYNTH_CALC]


def test_flag_off_engineering_case_l1_receives_real_calc(monkeypatch) -> None:
    _patch_compute(monkeypatch, _SYNTH_CALC)
    client = _StageRoutingStreamClient(understand_json=_fallarbeit())
    pipeline, gen = _pipeline(client, suppress=False)

    result = _run(pipeline, "RWDR 45x62x8, welches Material bei Hydraulikoel?")

    assert result.route_name == "engineering_case"
    assert gen.l1_calcs == [_SYNTH_CALC]


# ── 6: the Phase-3B draft-streaming L1 call site gets the SAME suppression -------------------------


def test_flag_on_general_knowledge_streaming_path_receives_empty_calc(
    monkeypatch,
) -> None:
    _patch_compute(monkeypatch, _SYNTH_CALC)
    client = _StageRoutingStreamClient(understand_json=_wissensfrage())
    pipeline, gen = _pipeline(client, suppress=True, draft_streaming=True)

    tokens: list[tuple[str, bool]] = []

    def _sink(delta: str, draft: bool) -> None:
        tokens.append((delta, draft))

    result = _run(pipeline, "Was ist eine Dichtung allgemein?", token_sink=_sink)

    assert result.route_name == "general_sealing_knowledge"
    # The draft-STREAMING L1 call site was the one exercised, and it too got an empty calc.
    assert gen.calls and gen.calls[0][0] == "stream"
    assert gen.l1_calcs == [CalcResult()]
    assert tokens  # draft deltas actually streamed (the streaming path really ran)
    # Payload transparency unchanged on the streaming path too.
    assert result.not_computed == (_UMFANG_NOT_COMPUTED,)


def test_flag_on_engineering_case_streaming_path_receives_real_calc(
    monkeypatch,
) -> None:
    _patch_compute(monkeypatch, _SYNTH_CALC)
    client = _StageRoutingStreamClient(understand_json=_fallarbeit())
    pipeline, gen = _pipeline(client, suppress=True, draft_streaming=True)

    result = _run(
        pipeline,
        "RWDR 45x62x8, welches Material bei Hydraulikoel?",
        token_sink=lambda d, draft: None,
    )

    assert result.route_name == "engineering_case"
    assert gen.calls and gen.calls[0][0] == "stream"
    assert gen.l1_calcs == [
        _SYNTH_CALC
    ]  # kernel=True: real calc even on the streaming path


# ── 4: guard contract + L3 verify() + response payload ALL keep the REAL calc (explicit) ----------


def test_guard_and_verify_share_answer_relevant_calc_while_payload_keeps_telemetry(
    monkeypatch,
) -> None:
    """An unsolicited result cannot be authorized after L1 suppression.

    Guard and verifier therefore see the same empty answer context; the response payload retains the
    real kernel result as internal/product telemetry.
    """
    _patch_compute(monkeypatch, _SYNTH_CALC)

    # Capture the calc that L3 verify() is handed.
    captured_verify: dict[str, object] = {}
    _real_verify = stages.verify

    async def _spy_verify(*args, **kwargs):
        captured_verify["calc"] = kwargs.get("calc")
        captured_verify["computed_values"] = kwargs.get("computed_values")
        captured_verify["not_computed"] = kwargs.get("not_computed")
        return await _real_verify(*args, **kwargs)

    monkeypatch.setattr(stages, "verify", _spy_verify)

    # Capture the calc the guard contract is built from. It is imported locally inside run() from
    # sealai_v2.core.response_contract, so patching the module attribute intercepts it at call time.
    import sealai_v2.core.response_contract as _rc_mod

    captured_guard: dict[str, object] = {}
    _real_build_guard = _rc_mod.build_guard_contract

    def _spy_build_guard(*args, **kwargs):
        captured_guard["calc"] = kwargs.get("calc")
        return _real_build_guard(*args, **kwargs)

    monkeypatch.setattr(_rc_mod, "build_guard_contract", _spy_build_guard)

    client = _StageRoutingStreamClient(understand_json=_wissensfrage())
    cat = load_traps()
    gen = _CalcSpyGenerator(
        client, PromptAssembler(), ModelConfig("fake-l1", stage="l1")
    )
    verifier = L3Verifier(
        client, VerifierPromptAssembler(), ModelConfig("fake-l3", stage="verifier"), cat
    )
    pipeline = Pipeline(
        generator=gen,
        client=client,
        helper_model=ModelConfig("fake-helper", stage="understand"),
        understand_enabled=True,
        verifier=verifier,
        catalog=cat,
        route_optimization_enabled=True,
        suppress_calc_for_non_kernel_routes_enabled=True,
        # Turn on the response-contract + general guard path so build_guard_contract is reached.
        response_contract_enabled=True,
        response_contract_general_guard_enabled=True,
    )

    result = _run(pipeline, "Was ist eine Dichtung allgemein?")

    assert result.route_name == "general_sealing_knowledge"
    # L1 PROMPT: suppressed (empty).
    assert gen.l1_calcs and all(c == CalcResult() for c in gen.l1_calcs)
    # L3 and the guard share L1's answer-relevance boundary; neither can authorize the suppressed
    # kernel tangent after generation.
    assert captured_verify["calc"] == CalcResult()
    assert captured_verify["not_computed"] == ()
    assert captured_guard["calc"] == CalcResult()
    # Response payload: reflects the REAL calc for transparency/telemetry.
    assert result.not_computed == (_UMFANG_NOT_COMPUTED,)
