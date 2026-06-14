"""M8 (trust-spine completion) — Part 5: the decision rests on the kernel value.

Proof (not new wiring) that the kernel's deterministic value, settled from memory inputs, reaches
BOTH the L1 prompt AND the L3 verification context AND the briefing in ONE run; that a corrected
input evicts the stale value from the next decision (and from the persisted slice); and that the
landed ``parametric_computation`` defense still fires when an L1 draft self-computes a kern quantity
(the guard is not weakened). Scripted fakes only — NO LLM, NO tokens. End-to-end LLM behaviour is
the post-arc owner-gated eval REPLAY.
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.calc.leak_detector import detect_parametric_leaks
from sealai_v2.core.contracts import (
    Answer,
    ComputedValue,
    Flags,
    ModelConfig,
    SessionContext,
    VerifierAction,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier, run_verify
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.render.renderer import ArtifactRenderer, snapshot_from_result
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient

_CLEAN_VERDICT = json.dumps({"findings": [], "verdict": "clean"})


def _seed(mem: InProcessConversationMemory, d_mm: str, n: str) -> None:
    mem.edit_fact(
        tenant_id="t",
        session_id="s",
        feld="wellendurchmesser",
        wert=d_mm,
        provenance="user-form",
    )
    mem.edit_fact(
        tenant_id="t", session_id="s", feld="drehzahl", wert=n, provenance="user-form"
    )


# --- one run: the kernel value reaches L1 prompt AND L3 context -----------------------------------


def test_settled_inputs_reach_l1_prompt_and_l3_context_in_one_run():
    l1 = FakeLlmClient("ok")  # L1 draft (no number → no leak → L3 PASS)
    l3 = FakeLlmClient(_CLEAN_VERDICT)  # L3 critic: clean
    cat = load_traps()
    p = Pipeline(
        generator=L1Generator(l1, PromptAssembler(), ModelConfig("fake-l1")),
        client=l1,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        verifier=L3Verifier(l3, VerifierPromptAssembler(), ModelConfig("fake-l3"), cat),
        catalog=cat,
        memory=InProcessConversationMemory(),
    )
    _seed(p.memory, "50 mm", "4000 U/min")  # v = π·50·4000/60000 ≈ 10.472
    asyncio.run(
        p.run("Wie hoch ist v?", tenant=TenantContext("t"), session=SessionContext("s"))
    )

    # L1: the kern value + its input provenance are in the assembled L1 system prompt
    assert any(
        "10.472" in c["system"] and "wellendurchmesser" in c["system"] for c in l1.calls
    )
    # L3: the same kern value is in the verifier's context (it verifies L1 AGAINST the kern-fact)
    assert any("10.472" in c["system"] for c in l3.calls)


# --- the briefing rests on the kernel value -------------------------------------------------------


def test_settled_inputs_reach_the_briefing():
    l1 = FakeLlmClient("ok")
    p = Pipeline(
        generator=L1Generator(l1, PromptAssembler(), ModelConfig("fake-l1")),
        client=l1,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
    )
    _seed(p.memory, "50 mm", "4000 U/min")
    res = asyncio.run(
        p.run("Brief?", tenant=TenantContext("t"), session=SessionContext("s"))
    )
    art = ArtifactRenderer().briefing(snapshot_from_result("Brief?", res))
    assert (
        "10.47" in art.body
    )  # the deterministic kern value is in the suitability artifact


# --- a corrected input evicts the stale value from the decision + the persisted slice -------------


def test_corrected_input_evicts_stale_v_from_decision_and_persisted_slice():
    l1 = FakeLlmClient("ok")
    p = Pipeline(
        generator=L1Generator(l1, PromptAssembler(), ModelConfig("fake-l1")),
        client=l1,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
    )
    tenant, session = TenantContext("t"), SessionContext("s")
    _seed(p.memory, "50 mm", "4000 U/min")  # v ≈ 10.472
    asyncio.run(p.run("v?", tenant=tenant, session=session))
    assert any("10.472" in c["system"] for c in l1.calls)  # first decision used 10.472

    # correct the diameter (chip edit) → recompute persists the new value
    p.memory.edit_fact(
        tenant_id="t",
        session_id="s",
        feld="wellendurchmesser",
        wert="80 mm",
        provenance="user-edited",
    )
    p.recompute_derived_for(tenant_id="t", session_id="s")
    persisted = {
        x.calc_id: x for x in p.memory.derived_facts(tenant_id="t", session_id="s")
    }
    assert (
        abs(persisted["umfangsgeschwindigkeit"].value - 16.755) < 0.01
    )  # new value persisted

    l1.calls.clear()  # isolate the SECOND decision
    asyncio.run(p.run("v jetzt?", tenant=tenant, session=session))
    # the next decision uses the fresh value (π·80·4000/60000 ≈ 16.755) — the stale 10.472 is gone
    assert any("16.755" in c["system"] for c in l1.calls)
    assert all("10.472" not in c["system"] for c in l1.calls)


# --- the parametric_computation guard still fires (re-pin — never weakened) -----------------------


def test_self_computed_number_contradicting_kernel_is_caught():
    """Deterministic guard, agent-final: with the kern value present (10.472), a draft asserting a
    DIFFERENT self-computed v is a leak (outside the ≤2 % restate tolerance)."""
    cv = (
        ComputedValue(
            calc_id="umfangsgeschwindigkeit",
            name="v_m_s",
            value=10.472,
            unit="m/s",
            stage=1,
            derivation_depth=1,
        ),
    )
    leaks = detect_parametric_leaks(
        "Die Umfangsgeschwindigkeit beträgt rund 99,9 m/s.", computed_values=cv
    )
    assert leaks and leaks[0].calc_id == "umfangsgeschwindigkeit"


def test_run_verify_corrects_a_self_computed_leak_when_kernel_present():
    """Integration: the leaked self-computed number never survives — regenerate-once against the
    kern-fact, and the leaked '99,9' is gone from the final answer."""
    cv = (
        ComputedValue(
            calc_id="umfangsgeschwindigkeit",
            name="v_m_s",
            value=10.472,
            unit="m/s",
            stage=1,
            derivation_depth=1,
        ),
    )
    cat = load_traps()
    draft = Answer(
        text="Die Umfangsgeschwindigkeit beträgt rund 99,9 m/s.", model="fake-l1"
    )
    gen = L1Generator(
        FakeLlmClient(
            "Die Umfangsgeschwindigkeit lasse ich deterministisch berechnen — der "
            "Rechenkern liefert rund 10,47 m/s."
        ),
        PromptAssembler(),
        ModelConfig("fake-l1"),
    )
    l3 = L3Verifier(
        ScriptedFakeLlmClient([_CLEAN_VERDICT, _CLEAN_VERDICT]),
        VerifierPromptAssembler(),
        ModelConfig("fake-l3"),
        cat,
    )
    ans, verdict = asyncio.run(
        run_verify(l3, gen, cat, "F", draft, flags=Flags(), computed_values=cv)
    )
    assert verdict.action in (VerifierAction.CORRECTED, VerifierAction.BLOCKED_HEDGE)
    assert (
        "99,9" not in ans.text
    )  # the leaked self-computed number never reaches the user
