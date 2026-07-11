"""L3 wired into the pipeline (stage 4) + the M1 divergence fixtures as executable tests.

These assert the MECHANISM end-to-end: given the catalog + a given L3 verdict, the final answer
no longer asserts the confident-wrong claim (TRAP-02) and a clean range answer is not blocked
(CALC-02). Whether the REAL verifier model catches TRAP-02 is the M2 acceptance gate, measured in
the live eval-REPLAY (after the build HALT) — not here.
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Flags, ModelConfig, VerifierAction
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier
from sealai_v2.eval.report import _asserts_epdm_polar
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.pipeline.pipeline import Pipeline, build_pipeline
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient

_T = TenantContext("eval-tenant")
_CLEAN = json.dumps({"findings": [], "verdict": "clean"})


def _violation(trap_id: str, gate: str) -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "trap_id": trap_id,
                    "gate": gate,
                    "violated": True,
                    "evidence": "Zitat",
                }
            ],
            "verdict": "violation",
        }
    )


def _pipeline(client, *, verify: bool = True) -> Pipeline:
    cat = load_traps() if verify else None
    gen = L1Generator(client, PromptAssembler(), ModelConfig("fake-l1"))
    verifier = (
        L3Verifier(client, VerifierPromptAssembler(), ModelConfig("fake-l3"), cat)
        if verify
        else None
    )
    return Pipeline(
        generator=gen,
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        verifier=verifier,
        catalog=cat,
    )


# --- divergence fixtures (item 5 headline, as executable mechanism tests) ----------------


def test_source_less_trap02_blocks_without_asserting_a_counterclaim():
    client = ScriptedFakeLlmClient(
        [
            "EPDM ist ein polarer Kautschuk, deshalb quillt es in Mineralöl.",  # the M1 error
            _violation("TRAP-EPDM-MINERALOEL", "confident_wrong"),
            "EPDM ist UNPOLAR und quillt in Mineralöl/Kohlenwasserstoffen — NBR oder FKM nehmen.",
            _CLEAN,
        ]
    )
    res = asyncio.run(
        _pipeline(client).run(
            "EPDM-O-Ringe quellen in Hydrauliköl. Woran liegt das?",
            tenant=_T,
            flags=Flags(),
        )
    )
    assert res.verified is True
    assert res.verifier.action == VerifierAction.BLOCKED_HEDGE
    assert not _asserts_epdm_polar(res.answer.text)
    assert "UNPOLAR" not in res.answer.text


def test_trap02_hedges_when_regeneration_still_wrong():
    client = ScriptedFakeLlmClient(
        [
            "EPDM ist ein polarer Kautschuk.",
            _violation("TRAP-EPDM-MINERALOEL", "confident_wrong"),
            "EPDM ist trotzdem polar.",  # regeneration failed to fix it
            _violation("TRAP-EPDM-MINERALOEL", "confident_wrong"),
        ]
    )
    res = asyncio.run(
        _pipeline(client).run("EPDM in Hydrauliköl?", tenant=_T, flags=Flags())
    )
    assert res.verifier.action == VerifierAction.BLOCKED_HEDGE
    assert res.answer.model == "l3-hedge"
    assert not _asserts_epdm_polar(res.answer.text)


def test_calc02_range_answer_is_not_false_flagged():
    client = ScriptedFakeLlmClient(
        [
            "Statische O-Ring-Verpressung liegt typisch bei ~15-25 %. Gegen die "
            "Nut-Auslegungsnorm/Herstellertabelle verifizieren.",
            _CLEAN,  # an omission is NOT invented_precision → L3 returns clean
        ]
    )
    res = asyncio.run(
        _pipeline(client).run(
            "Wie viel Verpressung soll mein statischer O-Ring haben?",
            tenant=_T,
            flags=Flags(),
        )
    )
    assert res.verifier.action == VerifierAction.PASS
    assert res.answer.text.startswith("Statische")  # unchanged
    assert len(client.calls) == 2  # L1 + one verify; no regeneration


# --- always-on / flags-don't-gate / kill-switch -----------------------------------------


def test_l3_is_always_on_by_default():
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    assert p.verifier is not None and p.catalog is not None


def test_kill_switch_disables_l3_and_passes_draft_through():
    p = build_pipeline(Settings(verify_enabled=False), FakeLlmClient("DRAFT"))
    res = asyncio.run(p.run("Frage?", tenant=_T, flags=Flags()))
    assert p.verifier is None
    assert res.verified is False and res.verifier is None
    assert res.answer.text == "DRAFT"


def test_flags_do_not_gate_l3():
    # L3 runs regardless of the flag column (it is core, not flag-gated)
    for flags in (Flags(False, False), Flags(True, True)):
        client = ScriptedFakeLlmClient(["eine Antwort", _CLEAN])
        res = asyncio.run(_pipeline(client).run("Frage?", tenant=_T, flags=flags))
        assert res.verified is True and res.verifier.action == VerifierAction.PASS
