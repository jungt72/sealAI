"""Multi-turn eval runner (M6a) — the two consequential designs proven offline (scripted client):
the re-ask keystone (prior STATED facts carry into a later turn) and the memory_fabrication gate
(layered: runtime guard drops fabrication before the store; eval gate catches it if bypassed).
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ComputedValue, ModelConfig, RememberedFact
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.eval.multiturn import (
    MultiTurnCase,
    TurnSpec,
    load_multiturn_cases,
    run_multiturn_case,
    summarize_multiturn,
)
from sealai_v2.memory.distiller import DistillStats
from sealai_v2.security.tenant import TenantContext
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient

_T = TenantContext("eval-tenant")


def _mt_pipeline(client, *, memory=None, distiller="default") -> Pipeline:
    mem = memory if memory is not None else InProcessConversationMemory()
    dist = (
        Distiller(client, DistillPromptAssembler(), ModelConfig("fake-helper"))
        if distiller == "default"
        else distiller
    )
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        memory=mem,
        cross_session=InProcessCrossSessionMemory(),
        distiller=dist,
    )


def test_multiturn_re_ask_keystone_and_clean_memory():
    client = ScriptedFakeLlmClient(
        [
            "EPDM quillt in Hydrauliköl wegen Unpolarität.",  # t1 generate
            '{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}, '
            '{"feld": "temperatur", "wert": "150 °C"}]}',  # t1 distill
            "Bei höherer Temperatur zusätzlich Versprödung.",  # t2 generate
            '{"facts": []}',  # t2 distill
        ]
    )
    case = MultiTurnCase(
        id="MT-REASK-01",
        klass="Multi-Turn",
        turns=(
            TurnSpec(input="EPDM quillt in Hydrauliköl bei 150°C, warum?"),
            TurnSpec(
                input="und bei noch höherer Temperatur?",
                must_carry=("Hydrauliköl", "150"),
            ),
        ),
    )
    res = asyncio.run(run_multiturn_case(_mt_pipeline(client), case, tenant=_T))
    assert (
        res.carry_ok
    )  # turn-2 carried medium + 150 °C → re-ask is structurally impossible
    assert res.memory_gate_clean  # 150 traces to turn 1 → no fabrication
    assert {f.feld for f in res.turns[1].case_state} == {"medium", "temperatur"}


def test_multiturn_runtime_guard_drops_fabrication_before_state():
    # layered defense (i): a distilled 1500 °C (user said 150) is dropped at runtime → never stored.
    client = ScriptedFakeLlmClient(
        [
            "Antwort 1",  # t1 generate
            '{"facts": [{"feld": "temperatur", "wert": "1500 °C"}]}',  # t1 distill — fabricated
        ]
    )
    case = MultiTurnCase(
        id="MT-GUARD-01", klass="Multi-Turn", turns=(TurnSpec(input="FKM bei 150°C?"),)
    )
    res = asyncio.run(run_multiturn_case(_mt_pipeline(client), case, tenant=_T))
    assert res.turns[0].case_state == ()  # guard dropped it
    assert res.memory_gate_clean


def test_multiturn_gate_catches_fabrication_if_runtime_bypassed():
    # backstop (ii): seed a fabricated fact directly into the store (simulating a runtime bypass),
    # run with no distiller → the eval gate must still flag memory_fabrication.
    mem = InProcessConversationMemory()
    mem.record_turn(
        tenant_id="eval-tenant",
        session_id="mt-MT-FAB-01",
        question="FKM bei 150°C",
        answer="x",
        facts=(RememberedFact("temperatur", "1500 °C"),),
    )
    client = ScriptedFakeLlmClient(["Antwort"])
    p = _mt_pipeline(client, memory=mem, distiller=None)
    case = MultiTurnCase(
        id="MT-FAB-01",
        klass="Multi-Turn",
        turns=(TurnSpec(input="FKM bei 150°C, und weiter?"),),
    )
    res = asyncio.run(run_multiturn_case(p, case, tenant=_T))
    assert not res.memory_gate_clean
    assert res.turns[0].memory_fabrication[0].feld == "temperatur"


# --- re-ask judge-half (owner clarification: keep BOTH halves) ------------------------------------
# The deterministic must_carry half proves the fact is PRESENT in the prompt; the judge half
# confirms the answer HONORED it (did not re-ask). A fake judge fn decouples this from the scripted
# LLM client (which only feeds generate + distill).


def _judge_reasking(*topics: str):
    """A judge that always reports the answer re-asked the given topics (violated)."""

    async def _fn(answer_text: str, already_known: tuple[str, ...]) -> dict[str, bool]:
        return {t: (t in topics) for t in already_known}

    return _fn


async def _judge_clean(
    answer_text: str, already_known: tuple[str, ...]
) -> dict[str, bool]:
    return {t: False for t in already_known}


def test_reask_judge_half_flags_a_reasking_answer():
    client = ScriptedFakeLlmClient(
        [
            "Welche Temperatur denn genau?",
            '{"facts": []}',
        ]  # t1 generate (re-asks!), t1 distill
    )
    # seed medium so it is already known going into turn 1
    mem = InProcessConversationMemory()
    mem.record_turn(
        tenant_id="eval-tenant",
        session_id="mt-MT-REASK-X",
        question="EPDM in Hydrauliköl",
        answer="ok",
        facts=(RememberedFact("medium", "Hydrauliköl"),),
    )
    case = MultiTurnCase(
        id="MT-REASK-X",
        klass="Multi-Turn",
        turns=(
            TurnSpec(
                input="und weiter?",
                must_carry=("Hydrauliköl",),
                must_not_reask=("medium",),
            ),
        ),
    )
    res = asyncio.run(
        run_multiturn_case(
            _mt_pipeline(client, memory=mem, distiller=None),
            case,
            tenant=_T,
            judge=_judge_reasking("medium"),
        )
    )
    assert res.turns[0].carry_ok  # deterministic half: fact IS present
    assert not res.turns[0].reask_ok  # judge half: answer re-asked it anyway
    assert "medium" in res.turns[0].reask_violations


def test_reask_judge_half_clean_answer_passes():
    client = ScriptedFakeLlmClient(
        ["Bei höherer Temperatur Versprödung.", '{"facts": []}']
    )
    mem = InProcessConversationMemory()
    mem.record_turn(
        tenant_id="eval-tenant",
        session_id="mt-MT-REASK-Y",
        question="EPDM in Hydrauliköl",
        answer="ok",
        facts=(RememberedFact("medium", "Hydrauliköl"),),
    )
    case = MultiTurnCase(
        id="MT-REASK-Y",
        klass="Multi-Turn",
        turns=(
            TurnSpec(
                input="und weiter?",
                must_carry=("Hydrauliköl",),
                must_not_reask=("medium",),
            ),
        ),
    )
    res = asyncio.run(
        run_multiturn_case(
            _mt_pipeline(client, memory=mem, distiller=None),
            case,
            tenant=_T,
            judge=_judge_clean,
        )
    )
    assert res.turns[0].carry_ok and res.turns[0].reask_ok


# --- summarize_multiturn: fold memory_fabrication into the Schranken quota (agent-final) ----------


def _clean_case() -> MultiTurnCase:
    return MultiTurnCase(
        id="MT-OK",
        klass="Multi-Turn",
        turns=(
            TurnSpec(
                input="FKM bei 150°C?",
                must_carry=("150",),
                must_not_reask=("temperatur",),
            ),
        ),
    )


def test_summarize_clean_memory_schranken_is_1_0():
    client = ScriptedFakeLlmClient(
        ["Antwort.", '{"facts": [{"feld": "temperatur", "wert": "150 °C"}]}']
    )
    res = asyncio.run(
        run_multiturn_case(
            _mt_pipeline(client), _clean_case(), tenant=_T, judge=_judge_clean
        )
    )
    s = summarize_multiturn([res])
    assert s.memory_schranken_quota == 1.0
    assert s.n_memory_violations == 0


def test_summarize_fabrication_drops_quota_below_1_verbatim():
    # bypass the runtime guard (distiller=None) + seed a fabricated number → the deterministic gate
    # must drop the quota. The verdict is the VERBATIM untraceable_numeric_facts() result — no tolerance.
    mem = InProcessConversationMemory()
    mem.record_turn(
        tenant_id="eval-tenant",
        session_id="mt-MT-FAB-S",
        question="FKM bei 150°C",
        answer="x",
        facts=(RememberedFact("temperatur", "1500 °C"),),
    )
    client = ScriptedFakeLlmClient(["Antwort."])
    case = MultiTurnCase(
        id="MT-FAB-S", klass="Multi-Turn", turns=(TurnSpec(input="FKM bei 150°C?"),)
    )
    res = asyncio.run(
        run_multiturn_case(
            _mt_pipeline(client, memory=mem, distiller=None), case, tenant=_T
        )
    )
    s = summarize_multiturn([res])
    assert s.memory_schranken_quota == 0.0
    assert s.n_memory_violations == 1


def test_summarize_carries_drop_stats():
    s = summarize_multiturn([], drop_stats=DistillStats(proposed=10, dropped=1))
    assert s.drop is not None and s.drop.drop_rate == 0.1


# --- M8 user-form provenance (CALC-USERFORM-PROV-01) ----------------------------------------------
# The parameter form writes case-state via edit_fact(provenance="user-form") — a path NO chat-turn
# case exercises (chat distills → distilled-from-conversation). This holdout seeds user-form facts,
# asks the velocity, and checks: the KERN computes it (not L1) AND the input origin stays honestly
# "user-form" (the Phase-2 binding._origin branch), never degraded. The form value is user-STATED, so
# it must NOT trip the memory_fabrication gate (which otherwise only knows chat turns).


def _calc_pipeline(client) -> Pipeline:
    from sealai_v2.core.calc.evaluator import CascadeCalcEngine

    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        distiller=None,  # form-seeded facts; the query states no numbers → nothing to distill
    )


def _userform_case(provenance: str = "user-form") -> MultiTurnCase:
    return MultiTurnCase(
        id="CALC-USERFORM-PROV-01",
        klass="Berechnung / Formular-Provenance",
        seed_facts=(
            RememberedFact("wellendurchmesser", "40 mm", provenance),
            RememberedFact("drehzahl", "8000 U/min", provenance),
        ),
        turns=(
            TurnSpec(
                input="Wie hoch ist die Umfangsgeschwindigkeit?",
                must_carry=("40", "8000"),
                must_compute=("umfangsgeschwindigkeit",),
            ),
        ),
        hard_gates=("parametric_computation", "memory_fabrication"),
    )


def _velocity(turn) -> ComputedValue | None:
    return next(
        (c for c in turn.computed_values if c.calc_id == "umfangsgeschwindigkeit"), None
    )


def test_userform_case_is_wired_into_the_seed_set():
    # the holdout case loads from the multi-turn seed file and carries the form seed (user-form).
    case = next(
        c for c in load_multiturn_cases() if c.id == "CALC-USERFORM-PROV-01"
    )
    assert case.holdout is True
    seed = {f.feld: f.provenance for f in case.seed_facts}
    assert seed["wellendurchmesser"] == "user-form" and seed["drehzahl"] == "user-form"


def test_userform_kern_computes_and_origin_is_honest():
    # GREEN: form-seeded user-form facts → the kern computes 16,76 m/s AND the input origin stays
    # "user-form" (honest attribution); the memory Schranke is clean (form input ≠ fabrication).
    res = asyncio.run(run_multiturn_case(_calc_pipeline(FakeLlmClient()), _userform_case(), tenant=_T))
    turn = res.turns[0]
    assert turn.carry_ok and turn.compute_ok  # kern FIRED for umfangsgeschwindigkeit
    v = _velocity(turn)
    assert v is not None and round(v.value, 2) == 16.76  # π·40·8000/60000, kern-sourced
    assert any("user-form" in o for o in v.input_origins)  # (b) honest form attribution carried
    assert res.memory_gate_clean  # form input is user-stated, not a fabrication


def test_userform_attribution_assertion_bites_on_degraded_provenance():
    # RED-on-regression: same fact WITHOUT the user-form origin (e.g. the Phase-2 binding branch is
    # lost → degraded to the generic "vom Nutzer genannt") — the honest-attribution assertion catches
    # it. The kern still computes; only the provenance attribution differs.
    res = asyncio.run(
        run_multiturn_case(
            _calc_pipeline(FakeLlmClient()),
            _userform_case(provenance="distilled-from-conversation"),
            tenant=_T,
        )
    )
    v = _velocity(res.turns[0])
    assert v is not None and round(v.value, 2) == 16.76  # kern unaffected
    assert not any("user-form" in o for o in v.input_origins)  # attribution assertion BITES
    assert all("genannt" in o for o in v.input_origins)  # degraded to the generic origin


def test_userform_compute_assertion_bites_on_unitless_input():
    # RED-on-regression: a form value missing its unit (binder fail-closed) → the kern does NOT
    # compute → must_compute bites; no fabricated velocity slips through.
    case = MultiTurnCase(
        id="CALC-USERFORM-PROV-UNITLESS",
        klass="x",
        seed_facts=(
            RememberedFact("wellendurchmesser", "40", "user-form"),  # no unit → fail-closed
            RememberedFact("drehzahl", "8000", "user-form"),
        ),
        turns=(
            TurnSpec(
                input="Wie hoch ist die Umfangsgeschwindigkeit?",
                must_compute=("umfangsgeschwindigkeit",),
            ),
        ),
    )
    res = asyncio.run(run_multiturn_case(_calc_pipeline(FakeLlmClient()), case, tenant=_T))
    assert not res.turns[0].compute_ok  # kern fail-closed → must_compute miss (bites)
    assert _velocity(res.turns[0]) is None
