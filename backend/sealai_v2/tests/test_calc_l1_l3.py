"""M4 injection: L1 'Berechnete Werte' block + L3 calc_violation (FLAG-only, never corrective)."""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import (
    Answer,
    CalcResult,
    ComputedValue,
    Flags,
    ModelConfig,
    NotComputed,
    VerifierAction,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier, run_verify
from sealai_v2.knowledge.traps import TrapCatalog, TrapEntry
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient


def test_l1_renders_berechnete_werte_block():
    fake = FakeLlmClient("A")
    gen = L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1"))
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="umfangsgeschwindigkeit",
                name="v_m_s",
                value=12.57,
                unit="m/s",
                stage=1,
                derivation_depth=1,
                formula="v = π·d·n",
            ),
        )
    )
    asyncio.run(gen.generate("Frage?", flags=Flags(), calc=calc))
    sys = fake.calls[-1]["system"]
    assert "Berechnete Werte" in sys and "v_m_s = 12.57 m/s" in sys


def test_l1_renders_not_computed_and_estimate_marking():
    fake = FakeLlmClient("A")
    gen = L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1"))
    calc = CalcResult(
        computed=(
            ComputedValue("pv_wert", "pv", 62.8, "bar·m/s", 2, 2, estimate=True),
        ),
        not_computed=(NotComputed("x", "nicht berechenbar: Eingaben fehlen (p_bar)"),),
    )
    asyncio.run(gen.generate("F", flags=Flags(), calc=calc))
    sys = fake.calls[-1]["system"]
    assert "Schätzwert" in sys and "nicht berechenbar" in sys


_R = TrapEntry(
    id="R1",
    trigger="t",
    wrong=("w",),
    correct="C",
    gates=("confident_wrong",),
    provenance=("eval:X",),
    review_state="reviewed",
)


def _cat() -> TrapCatalog:
    return TrapCatalog(entries=(_R,))


def _verifier(c) -> L3Verifier:
    return L3Verifier(c, VerifierPromptAssembler(), ModelConfig("fake-l3"), _cat())


def _gen(c) -> L1Generator:
    return L1Generator(c, PromptAssembler(), ModelConfig("fake-l1"))


def _cv():
    return (
        ComputedValue(
            calc_id="umfangsgeschwindigkeit",
            name="v_m_s",
            value=12.57,
            unit="m/s",
            stage=1,
            derivation_depth=1,
        ),
    )


def _calc_finding(ref: str = "v_m_s") -> str:
    return json.dumps(
        {
            "findings": [
                {"calc_violation": True, "calc": ref, "violated": True, "evidence": "x"}
            ],
            "verdict": "violation",
        }
    )


def test_calc_violation_flags_never_corrects():
    client = ScriptedFakeLlmClient([_calc_finding()])
    draft = Answer(text="ein Entwurf", model="fake-l1")
    ans, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _gen(client),
            _cat(),
            "F",
            draft,
            flags=Flags(),
            computed_values=_cv(),
        )
    )
    assert (
        verdict.action == VerifierAction.FLAG
    )  # calc contradiction never blocks/corrects
    assert ans is draft and len(client.calls) == 1  # no regeneration
    assert verdict.findings and verdict.findings[0].kind == "calc"


def test_calc_violation_unknown_ref_is_dropped():
    client = ScriptedFakeLlmClient(
        [_calc_finding("nope_calc")]
    )  # not an injected value
    raw = asyncio.run(_verifier(client).verify("F", "E", (), _cv()))
    assert raw.findings == ()


def test_computed_values_rendered_into_verifier_prompt():
    client = ScriptedFakeLlmClient([json.dumps({"findings": [], "verdict": "clean"})])
    asyncio.run(_verifier(client).verify("F", "E", (), _cv()))
    sys = client.calls[0]["system"]
    assert "Berechnete Werte" in sys and "v_m_s" in sys
