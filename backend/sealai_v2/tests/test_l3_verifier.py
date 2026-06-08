from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import (
    Answer,
    Flags,
    ModelConfig,
    VerifierAction,
    VerifierFinding,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import (
    L3Verifier,
    build_correction_note,
    build_hedge,
    run_verify,
)
from sealai_v2.knowledge.traps import TrapCatalog, TrapEntry
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_REVIEWED = TrapEntry(
    id="R1",
    trigger="EPDM in Mineralöl",
    wrong=("EPDM ist polar",),
    correct="EPDM ist UNPOLAR und quillt in Mineralöl; NBR/FKM nehmen.",
    gates=("confident_wrong", "walked_into_trap"),
    provenance=("eval:TRAP-02",),
    review_state="reviewed",
)
_DRAFT = TrapEntry(
    id="D1",
    trigger="VMQ Chemie",
    wrong=("VMQ ist breit chemisch beständig",),
    correct="",
    gates=("confident_wrong",),
    provenance=("model_knowledge:UNREVIEWED",),
    review_state="draft",
)


def _catalog() -> TrapCatalog:
    return TrapCatalog(entries=(_REVIEWED, _DRAFT))


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


_CLEAN = json.dumps({"findings": [], "verdict": "clean"})


def _verifier(client) -> L3Verifier:
    return L3Verifier(
        client, VerifierPromptAssembler(), ModelConfig("fake-l3"), _catalog()
    )


def _generator(client) -> L1Generator:
    return L1Generator(client, PromptAssembler(), ModelConfig("fake-l1"))


def _draft(text: str = "EPDM ist ein polarer Kautschuk.") -> Answer:
    return Answer(text=text, model="fake-l1")


def test_parse_maps_review_state_server_side():
    client = ScriptedFakeLlmClient([_violation("R1", "confident_wrong")])
    raw = asyncio.run(_verifier(client).verify("Frage?", "Entwurf"))
    assert len(raw.findings) == 1
    f = raw.findings[0]
    assert (
        f.trap_id == "R1" and f.review_state == "reviewed"
    )  # from catalog, not the LLM


def test_unknown_trap_id_is_dropped():
    client = ScriptedFakeLlmClient([_violation("ZZZ", "confident_wrong")])
    raw = asyncio.run(_verifier(client).verify("Frage?", "Entwurf"))
    assert raw.findings == ()  # never trust an id the catalog does not know


def test_unparseable_verdict_fails_safe_to_no_findings():
    client = ScriptedFakeLlmClient(["not json at all"])
    raw = asyncio.run(_verifier(client).verify("Frage?", "Entwurf"))
    assert raw.findings == () and raw.parse_ok is False


def test_clean_draft_passes_unchanged():
    client = ScriptedFakeLlmClient([_CLEAN])
    draft = _draft("eine saubere Antwort")
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _generator(client),
            _catalog(),
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.PASS
    assert answer is draft  # untouched
    assert len(client.calls) == 1  # only the verify call, no regeneration


def test_reviewed_violation_regenerates_and_corrects():
    client = ScriptedFakeLlmClient(
        [_violation("R1", "confident_wrong"), "EPDM ist UNPOLAR — NBR nehmen.", _CLEAN]
    )
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _generator(client),
            _catalog(),
            "Frage?",
            _draft(),
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.CORRECTED and verdict.regenerated
    assert answer.text == "EPDM ist UNPOLAR — NBR nehmen."
    # the regeneration carried the reviewed correct fact as a correction note
    assert (
        "geprüfte Fakten" in client.calls[1]["system"]
        or "Korrekturhinweis" in client.calls[1]["system"]
    )


def test_reviewed_violation_that_persists_hedges_not_asserts():
    client = ScriptedFakeLlmClient(
        [
            _violation("R1", "confident_wrong"),
            "EPDM ist immer noch polar (kaputt).",
            _violation("R1", "confident_wrong"),
        ]
    )
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _generator(client),
            _catalog(),
            "Frage?",
            _draft(),
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    assert answer.model == "l3-hedge"
    # integrity: the hedge does NOT assert the replacement fact, it hedges
    assert "unpolar" not in answer.text.lower()
    assert "verifizieren" in answer.text.lower()


def test_draft_only_match_flags_never_blocks():
    client = ScriptedFakeLlmClient([_violation("D1", "confident_wrong")])
    draft = _draft("VMQ hält alles aus.")
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _generator(client),
            _catalog(),
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.FLAG
    assert answer is draft  # a draft (unreviewed) entry may flag, never correct/block
    assert len(client.calls) == 1  # no regeneration triggered


def test_correction_note_is_reviewed_only():
    cat = _catalog()
    reviewed_finding = VerifierFinding("R1", "confident_wrong", "reviewed", "x")
    draft_finding = VerifierFinding("D1", "confident_wrong", "draft", "y")
    note = build_correction_note(cat, (reviewed_finding,))
    assert note is not None and "UNPOLAR" in note
    # a draft-only finding yields NO correction (cannot assert from unreviewed knowledge)
    assert build_correction_note(cat, (draft_finding,)) is None


def test_hedge_mentions_concern_without_asserting():
    h = build_hedge(
        (VerifierFinding("R1", "confident_wrong", "reviewed", "EPDM polar"),)
    )
    assert "Vorsicht" in h and "verifizieren" in h.lower()
