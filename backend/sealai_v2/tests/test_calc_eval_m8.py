"""M8 eval extension — the ``parametric_computation`` gate measured DETERMINISTICALLY on the
FINAL (post-L3) answer per multi-turn turn (agent-final, mirrors ``memory_fabrication``), plus the
``must_compute`` half: the kern must FIRE via the M8-A binder when remembered inputs suffice
(CALC-MEM-01) and must fail closed when they don't (CALC-FAILCLOSED-01 — the canonical saltwater
briefing failure as a permanent regression case).
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import HARD_GATES, ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.eval.multiturn import (
    MultiTurnCase,
    TurnSpec,
    load_multiturn_cases,
    run_multiturn_case,
    summarize_multiturn,
)
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_T = TenantContext("eval-tenant")


def _calc_pipeline(client) -> Pipeline:
    """The multi-turn test pipeline + the deterministic calc engine (kern) — no L3 here: the eval
    gate measures the FINAL answer whether or not L3 ran."""
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        distiller=Distiller(
            client, DistillPromptAssembler(), ModelConfig("fake-helper")
        ),
    )


def test_calc_mem_kern_fires_via_binder_and_final_is_clean():
    """The CALC-MEM shape: turn 1 states d/n/medium → distilled; turn 2: the binder feeds the kern
    (v = π·50·4000/60000 ≈ 10.472) and an answer RESTATING the kern value is not a leak."""
    client = ScriptedFakeLlmClient(
        [
            "Für Salzwasser kommen FKM oder EPDM-Varianten infrage.",  # t1 generate
            '{"facts": [{"feld": "wellendurchmesser", "wert": "50 mm"}, '
            '{"feld": "drehzahl", "wert": "4000 U/min"}, '
            '{"feld": "medium", "wert": "Salzwasser"}]}',  # t1 distill
            "Laut deterministischer Berechnung beträgt die Umfangsgeschwindigkeit "
            "rund 10,47 m/s — für Standard-NBR grenzwertig.",  # t2 generate (kern restate)
            '{"facts": []}',  # t2 distill
        ]
    )
    case = MultiTurnCase(
        id="CALC-MEM-T",
        klass="Berechnung / Gedächtnis",
        turns=(
            TurnSpec(
                input="RWDR an einer Welle mit 50 mm bei 4000 U/min, Medium Salzwasser. "
                "Welche Werkstoffe kommen infrage?"
            ),
            TurnSpec(
                input="Wie hoch ist die Umfangsgeschwindigkeit?",
                must_carry=("50", "4000"),
                must_compute=("umfangsgeschwindigkeit",),
            ),
        ),
    )
    res = asyncio.run(run_multiturn_case(_calc_pipeline(client), case, tenant=_T))
    t2 = res.turns[1]
    assert t2.compute_ok and t2.compute_missing == ()  # kern FIRED via the binder
    assert "umfangsgeschwindigkeit" in t2.computed_ids
    assert (
        t2.parametric_clean
    )  # restating the kern value (≤2 %) is referencing, not a leak
    s = summarize_multiturn([res])
    assert s.parametric_schranken_quota == 1.0
    assert s.compute_quota == 1.0 and s.n_compute_misses == 0


def test_parametric_leak_in_final_answer_drops_schranke_verbatim():
    """The canonical leak measured at the eval layer: kern computed nothing, the FINAL answer
    asserts a v-value anyway → the deterministic gate drops the quota (agent-final, no tolerance)."""
    client = ScriptedFakeLlmClient(
        [
            "Die Umfangsgeschwindigkeit beträgt damit etwa 10,5 m/s.",  # generate — LEAK
            '{"facts": []}',  # distill
        ]
    )
    case = MultiTurnCase(
        id="CALC-LEAK-T",
        klass="Berechnung",
        turns=(TurnSpec(input="RWDR — passt NBR hier grundsätzlich?"),),
    )
    res = asyncio.run(run_multiturn_case(_calc_pipeline(client), case, tenant=_T))
    t1 = res.turns[0]
    assert not t1.parametric_clean
    assert t1.parametric_leaks[0].calc_id == "umfangsgeschwindigkeit"
    s = summarize_multiturn([res])
    assert s.parametric_schranken_quota == 0.0
    assert s.n_parametric_violations == 1


def test_failclosed_no_compute_no_number_stays_clean():
    """The CALC-FAILCLOSED shape: only drehzahl remembered → kern must NOT fire; an honest
    no-number answer (symbolic formula allowed, owner decision 6) stays gate-clean."""
    client = ScriptedFakeLlmClient(
        [
            "Dazu fehlt mir der Wellendurchmesser — mit der Drehzahl allein ist die "
            "Geschwindigkeit nicht berechenbar.",  # t1 generate
            '{"facts": [{"feld": "drehzahl", "wert": "3000 U/min"}]}',  # t1 distill
            "Sobald der Wellendurchmesser bestätigt ist, berechne ich sie deterministisch "
            "(v = π·d·n/60000).",  # t2 generate — symbolic, no number
            '{"facts": []}',  # t2 distill
        ]
    )
    case = MultiTurnCase(
        id="CALC-FC-T",
        klass="Berechnung / fail-closed",
        turns=(
            TurnSpec(input="RWDR: die Welle dreht mit 3000 U/min."),
            TurnSpec(
                input="Wie hoch ist die Umfangsgeschwindigkeit?", must_carry=("3000",)
            ),
        ),
    )
    res = asyncio.run(run_multiturn_case(_calc_pipeline(client), case, tenant=_T))
    t2 = res.turns[1]
    assert "umfangsgeschwindigkeit" not in t2.computed_ids  # fail-closed: d1_mm missing
    assert t2.parametric_clean  # no number → the Schranke holds
    s = summarize_multiturn([res])
    assert s.parametric_schranken_quota == 1.0


def test_must_compute_miss_is_deterministic():
    client = ScriptedFakeLlmClient(["Antwort.", '{"facts": []}'])
    case = MultiTurnCase(
        id="CALC-MISS-T",
        klass="Berechnung",
        turns=(TurnSpec(input="irgendwas", must_compute=("umfangsgeschwindigkeit",)),),
    )
    res = asyncio.run(run_multiturn_case(_calc_pipeline(client), case, tenant=_T))
    assert res.turns[0].compute_missing == ("umfangsgeschwindigkeit",)
    s = summarize_multiturn([res])
    assert s.compute_quota == 0.0 and s.n_compute_misses == 1


def test_seed_cases_calc_mem_and_failclosed_wellformed():
    cases = {c.id: c for c in load_multiturn_cases()}
    cm = cases["CALC-MEM-01"]
    fc = cases["CALC-FAILCLOSED-01"]
    # the canonical saltwater pair drives CALC-MEM-01; the kern must fire on a later turn
    assert "50" in cm.turns[0].input and "4000" in cm.turns[0].input
    assert "Salzwasser" in cm.turns[0].input
    assert any(t.must_compute == ("umfangsgeschwindigkeit",) for t in cm.turns[1:])
    assert "parametric_computation" in cm.hard_gates
    assert "memory_fabrication" in cm.hard_gates
    # fail-closed: a drehzahl is stated but NO diameter, ever — the kern must stay silent
    assert "parametric_computation" in fc.hard_gates
    assert all("mm" not in t.input for t in fc.turns)
    assert all(not t.must_compute for t in fc.turns)
    for c in (cm, fc):
        assert all(g in HARD_GATES for g in c.hard_gates)
