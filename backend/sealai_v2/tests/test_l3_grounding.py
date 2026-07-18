"""L3 + L2 grounding: card contradictions are FLAG-only (never corrective); only an INJECTED card
can be contradicted; a reviewed TRAP still drives the correction (integrity unchanged)."""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import (
    Answer,
    Flags,
    GroundingFact,
    ModelConfig,
    VerifierAction,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier, run_verify
from sealai_v2.knowledge.traps import TrapCatalog, TrapEntry
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_R = TrapEntry(
    id="R1",
    trigger="EPDM in Mineralöl",
    wrong=("EPDM ist polar",),
    correct="EPDM ist UNPOLAR; NBR/FKM nehmen.",
    gates=("confident_wrong",),
    provenance=("eval:TRAP-02",),
    review_state="reviewed",
    sources=("test-source",),
)


def _cat() -> TrapCatalog:
    return TrapCatalog(entries=(_R,))


def _verifier(c) -> L3Verifier:
    return L3Verifier(c, VerifierPromptAssembler(), ModelConfig("fake-l3"), _cat())


def _gen(c) -> L1Generator:
    return L1Generator(c, PromptAssembler(), ModelConfig("fake-l1"))


def _draft(t: str = "ein Entwurf, der EPDM für Öl empfiehlt") -> Answer:
    return Answer(text=t, model="fake-l1")


def _gf():
    return (
        GroundingFact(
            text="EPDM ist unpolar und quillt in Mineralöl.",
            quelle="Fachkarte FK-EPDM-MINERALOEL (reviewed)",
            card_id="FK-EPDM-MINERALOEL",
        ),
    )


def _card_finding(cid: str = "FK-EPDM-MINERALOEL") -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "card_contradiction": True,
                    "card_id": cid,
                    "violated": True,
                    "evidence": "EPDM ist polar",
                }
            ],
            "verdict": "violation",
        }
    )


_CLEAN = json.dumps({"findings": [], "verdict": "clean"})


def test_card_contradiction_flags_never_corrects():
    client = ScriptedFakeLlmClient([_card_finding()])
    draft = _draft()
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _gen(client),
            _cat(),
            "F",
            draft,
            flags=Flags(),
            grounding_facts=_gf(),
        )
    )
    assert (
        verdict.action == VerifierAction.FLAG
    )  # a card contradiction never blocks/corrects
    assert answer is draft  # unchanged
    assert len(client.calls) == 1  # no regeneration
    assert verdict.findings and verdict.findings[0].kind == "card"


def test_card_contradiction_unknown_id_is_dropped():
    # the model names a card that was NOT injected → cannot be trusted → dropped
    client = ScriptedFakeLlmClient([_card_finding("FK-NOT-INJECTED")])
    raw = asyncio.run(_verifier(client).verify("F", "E", _gf()))
    assert raw.findings == ()


def test_reviewed_trap_still_drives_correction_with_card_alongside():
    both = json.dumps(
        {
            "findings": [
                {
                    "card_contradiction": True,
                    "card_id": "FK-EPDM-MINERALOEL",
                    "violated": True,
                    "evidence": "x",
                },
                {
                    "trap_id": "R1",
                    "gate": "confident_wrong",
                    "violated": True,
                    "evidence": "y",
                },
            ],
            "verdict": "violation",
        }
    )
    client = ScriptedFakeLlmClient([both, "EPDM ist UNPOLAR — NBR nehmen.", _CLEAN])
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _gen(client),
            _cat(),
            "F",
            _draft(),
            flags=Flags(),
            grounding_facts=_gf(),
        )
    )
    assert (
        verdict.action == VerifierAction.CORRECTED
    )  # the reviewed TRAP drove it, not the card
    assert answer.text == "EPDM ist UNPOLAR — NBR nehmen."


def test_grounding_facts_rendered_into_verifier_prompt():
    client = ScriptedFakeLlmClient([_CLEAN])
    asyncio.run(_verifier(client).verify("F", "E", _gf()))
    sys_prompt = client.calls[0]["system"]
    assert "Geerdete Fakten" in sys_prompt
    assert "FK-EPDM-MINERALOEL" in sys_prompt
