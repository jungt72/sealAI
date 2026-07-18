"""I6 holistic guard: L3 never adds free content — every note/hedge is a reconstructable function of
reviewed catalog fields / kern results / matrix cell text, and the final answer's model is never the
verifier's. Model: the Gegencheck non-affirmation tests (test_gegencheck.py, ``_FORBIDDEN_KEYS``).

Spec derived in the INC-GEGENCHECK-CORE / L3-additivity forensic audits (read-only); this is the
build. Covers every note/hedge builder + all four ``run_verify`` return paths, so a future change
that lets a note/hedge echo the verifier model's free text, or that concatenates L1+L3 prose, fails
loudly here rather than surfacing later as a doctrine drift.
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.calc.leak_detector import LeakFinding, detect_parametric_leaks
from sealai_v2.core.contracts import (
    Answer,
    ComputedValue,
    Flags,
    GroundingFact,
    ModelConfig,
    VerifierAction,
    VerifierFinding,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import (
    L3Verifier,
    build_calc_leak_hedge,
    build_calc_leak_note,
    build_correction_note,
    build_hedge,
    build_matrix_correction_note,
    build_matrix_hedge,
    build_overlimit_hedge,
    build_overlimit_note,
    run_verify,
)
from sealai_v2.knowledge.traps import TrapCatalog, TrapEntry
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

# A finding whose ``evidence`` carries a free-formulated, fabricated claim + number — exactly what
# I6 forbids from reaching the user. No builder may ever surface this string.
_FABRICATED_EVIDENCE = "Der exakte Grenzwert beträgt hier erfunden 47,3 bar laut meiner eigenen Einschätzung."


def _catalog(
    correct: str = "EPDM ist UNPOLAR und quillt in Mineralöl; NBR/FKM nehmen.",
) -> TrapCatalog:
    entry = TrapEntry(
        id="R1",
        trigger="EPDM in Mineralöl",
        wrong=("EPDM ist polar",),
        correct=correct,
        gates=("confident_wrong", "walked_into_trap"),
        provenance=("eval:TRAP-02",),
        review_state="reviewed",
        sources=("test-source",),
    )
    return TrapCatalog(entries=(entry,))


def _finding(
    kind: str = "trap", trap_id: str = "R1", gate: str = "confident_wrong"
) -> VerifierFinding:
    return VerifierFinding(trap_id, gate, "reviewed", _FABRICATED_EVIDENCE, kind)


def _verifier(client, catalog: TrapCatalog) -> L3Verifier:
    return L3Verifier(
        client, VerifierPromptAssembler(), ModelConfig("fake-l3"), catalog
    )


def _generator(client, model: str = "fake-l1") -> L1Generator:
    return L1Generator(client, PromptAssembler(), ModelConfig(model))


def _violation_json(trap_id: str = "R1", gate: str = "confident_wrong") -> str:
    return json.dumps(
        {
            "findings": [
                {"trap_id": trap_id, "gate": gate, "violated": True, "evidence": "x"}
            ],
            "verdict": "violation",
        }
    )


_CLEAN = json.dumps({"findings": [], "verdict": "clean"})


# ---------------------------------------------------------------------------
# 1 — correction_note never carries the verifier model's free-formulated evidence
# ---------------------------------------------------------------------------


def test_correction_note_never_carries_model_evidence():
    note = build_correction_note(_catalog(), (_finding(),))
    assert note is not None
    assert _FABRICATED_EVIDENCE not in note


# ---------------------------------------------------------------------------
# 2 + 3 — the note is an EXACT, deterministic reconstruction of the catalog field; changing the
# reviewed field changes the note by precisely that substring, mechanically, without any model call
# ---------------------------------------------------------------------------


def test_correction_note_is_exact_reconstruction_of_the_catalog_field():
    cat = _catalog()
    note = build_correction_note(cat, (_finding(),))
    entry = cat.by_id("R1")
    assert note == (
        "Die Verifikation (L3) hat in deinem Entwurf eine bekannte Falle / einen "
        "selbstbewusst-falschen Mechanismus markiert. Korrigiere die Antwort und stütze dich "
        "dabei AUSSCHLIESSLICH auf diese geprüften Fakten (keine eigene Gegenbehauptung "
        "erfinden):\n- " + entry.correct
    )


def test_correction_note_changes_mechanically_with_the_catalog_field_nothing_else():
    note_a = build_correction_note(_catalog(correct="FAKT A."), (_finding(),))
    note_b = build_correction_note(_catalog(correct="FAKT B."), (_finding(),))
    assert note_a != note_b
    assert "FAKT A." in note_a and "FAKT A." not in note_b
    assert "FAKT B." in note_b and "FAKT B." not in note_a
    # the diff between the two notes is EXACTLY the substituted fact — nothing model-formulated
    # was interleaved
    assert note_a.replace("FAKT A.", "X") == note_b.replace("FAKT B.", "X")


# ---------------------------------------------------------------------------
# 4 + 5 — every hedge builder: exact reconstruction from known fields, never the model's evidence
# ---------------------------------------------------------------------------


def test_trap_hedge_with_catalog_is_exact_reconstruction_and_omits_model_evidence():
    cat = _catalog()
    h = build_hedge((_finding(),), cat)
    entry = cat.by_id("R1")
    assert h == (
        "⚠️ Hier ist Vorsicht geboten. Nach geprüftem Stand gilt:\n"
        "- " + entry.correct + "\n"
        "Das ist nur eine ingenieurtechnische Orientierung — "
        "bitte gegen das Datenblatt des konkreten Werkstoffs bzw. mit dem Hersteller "
        "verifizieren; keine Freigabe."
    )
    assert _FABRICATED_EVIDENCE not in h


def test_trap_hedge_without_catalog_is_the_fixed_generic_string():
    h = build_hedge((), None)
    assert h == (
        "⚠️ Hier ist Vorsicht geboten. Zu diesem Punkt kann ich ohne eine geprüfte Quelle "
        "keine belastbare Aussage treffen — bitte gegen das Datenblatt des konkreten Werkstoffs "
        "bzw. mit dem Hersteller verifizieren. Das ist nur eine Orientierung, keine Freigabe."
    )


def test_matrix_note_and_hedge_are_grounded_in_the_cell_text_only():
    cell = GroundingFact(
        text="FKM x Heißdampf: unverträglich (Hydrolyse).",
        quelle="Matrix-Zelle MX-1",
        card_id="MX-1",
    )
    f = _finding(kind="matrix", trap_id="MX-1")
    note = build_matrix_correction_note((cell,), (f,))
    hedge = build_matrix_hedge((cell,), (f,))
    assert note is not None
    assert cell.text in note and cell.quelle in note
    assert cell.text in hedge
    assert _FABRICATED_EVIDENCE not in note
    assert _FABRICATED_EVIDENCE not in hedge


def test_calc_leak_note_and_hedge_are_grounded_in_the_kern_result_only():
    leak = LeakFinding(
        calc_id="umfangsgeschwindigkeit",
        value_text="16,76 m/s",
        excerpt=_FABRICATED_EVIDENCE,
    )
    cv = (
        ComputedValue(
            calc_id="umfangsgeschwindigkeit",
            name="v",
            value=16.755,
            unit="m/s",
            stage=1,
            derivation_depth=0,
        ),
    )
    note = build_calc_leak_note((leak,), computed_values=cv)
    hedge = build_calc_leak_hedge((leak,), computed_values=cv)
    assert (
        "16.755" in note and "16.755" in hedge
    )  # the kern's own value, not the leak's own text
    assert _FABRICATED_EVIDENCE not in note
    assert _FABRICATED_EVIDENCE not in hedge


def test_overlimit_note_and_hedge_are_qualitative_no_model_evidence_no_threshold_number():
    findings = (
        VerifierFinding(
            "calc_overlimit:umfangsgeschwindigkeit",
            "confident_wrong",
            "reviewed",
            _FABRICATED_EVIDENCE,
            "calc_overlimit",
        ),
    )
    cv = (
        ComputedValue(
            calc_id="umfangsgeschwindigkeit",
            name="v",
            value=25.0,
            unit="m/s",
            stage=1,
            derivation_depth=0,
            warnings=("belastungsgrenze überschritten",),
        ),
    )
    note = build_overlimit_note(findings, cv)
    hedge = build_overlimit_hedge(findings, cv)
    assert note is not None
    assert "25.0" in note and "25.0" in hedge  # the kern's own computed v
    assert _FABRICATED_EVIDENCE not in note
    assert _FABRICATED_EVIDENCE not in hedge
    assert (
        "47,3 bar" not in note and "47,3 bar" not in hedge
    )  # no fabricated threshold number


# ---------------------------------------------------------------------------
# 6 — no ``run_verify`` return path merges/concatenates L1 prose with L3 prose
# ---------------------------------------------------------------------------


def test_pass_path_returns_the_draft_object_unchanged():
    cat = _catalog()
    client = ScriptedFakeLlmClient([_CLEAN])
    draft = Answer(text="Saubere Antwort ohne Fallen.", model="gpt-5.1")
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client, cat),
            _generator(client),
            cat,
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.PASS
    assert answer is draft  # identity — not a copy, not a merge


def test_flag_path_returns_the_draft_object_unchanged():
    draft_entry = TrapEntry(
        id="D1",
        trigger="x",
        wrong=("x",),
        correct="",
        gates=("confident_wrong",),
        provenance=("model_knowledge:UNREVIEWED",),
        review_state="draft",
    )
    cat = TrapCatalog(entries=(_catalog().by_id("R1"), draft_entry))
    client = ScriptedFakeLlmClient([_violation_json("D1")])
    draft = Answer(
        text="Ein Entwurf mit einem ungereviewten Verdacht.", model="gpt-5.1"
    )
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client, cat),
            _generator(client),
            cat,
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.FLAG
    assert answer is draft


def test_corrected_path_answer_is_the_generators_own_completion_verbatim():
    cat = _catalog()
    regen_text = "EPDM ist UNPOLAR — NBR nehmen."
    client = ScriptedFakeLlmClient([_violation_json(), regen_text, _CLEAN])
    draft = Answer(text="EPDM ist ein polarer Kautschuk.", model="gpt-5.1")
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client, cat),
            _generator(client),
            cat,
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.CORRECTED
    # L1's own completion is used VERBATIM — the correction note travelled only as INPUT to L1's
    # generation, it is never appended/prefixed to L1's output
    assert answer.text == regen_text
    assert (
        cat.by_id("R1").correct not in answer.text
    )  # not the raw catalog text, L1's own words
    assert draft.text not in answer.text  # not the rejected draft either


def test_blocked_hedge_path_answer_is_the_hedge_string_exactly_never_prefixed_with_the_draft():
    cat = _catalog()
    client = ScriptedFakeLlmClient(
        [_violation_json(), "immer noch falsch formuliert", _violation_json()]
    )
    draft = Answer(text="EPDM ist ein polarer Kautschuk.", model="gpt-5.1")
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client, cat),
            _generator(client),
            cat,
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    expected = build_hedge(
        (VerifierFinding("R1", "confident_wrong", "reviewed", "x", "trap"),), cat
    )
    assert answer.text == expected
    assert draft.text not in answer.text
    assert "immer noch falsch formuliert" not in answer.text


# ---------------------------------------------------------------------------
# 7 — a nicht-kern INTEGER (not just a float) assertion is caught by the runtime leak scanner.
# Pins the int-capable behaviour of ``_NUM`` so a future edit cannot silently narrow it back to
# float-only (the STATIC I5a architecture scanner is float-only by design; the RUNTIME L3 guard is
# not, and this test is the guard against that distinction eroding unnoticed).
# ---------------------------------------------------------------------------


def test_runtime_leak_detector_catches_an_integer_assertion_not_just_floats():
    draft_text = "Die Umfangsgeschwindigkeit beträgt 5 m/s."
    cv = (
        ComputedValue(
            calc_id="umfangsgeschwindigkeit",
            name="v",
            value=16.755,
            unit="m/s",
            stage=1,
            derivation_depth=0,
        ),
    )
    leaks = detect_parametric_leaks(draft_text, computed_values=cv)
    assert (
        leaks
    )  # the bare integer "5" for a kern-owned quantity is caught, not just decimals


# ---------------------------------------------------------------------------
# 9 — the final answer's model is always L1's model or the deterministic hedge sentinel, NEVER the
# verifier's model. Structural guarantee (pipeline.py wires generator/verifier from separate
# LlmClient instances); pinned here at the l3_verifier boundary with distinct model strings so a
# future wiring mistake fails loudly instead of silently mixing roles.
# ---------------------------------------------------------------------------


def test_final_answer_model_is_never_the_verifier_model_pass_path():
    cat = _catalog()
    client = ScriptedFakeLlmClient([_CLEAN])
    draft = Answer(text="Saubere Antwort.", model="gpt-5.1")
    answer, _ = asyncio.run(
        run_verify(
            _verifier(client, cat),
            _generator(client, "gpt-5.1"),
            cat,
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert answer.model == "gpt-5.1"
    assert answer.model != "mistral-small-2603"


def test_final_answer_model_is_never_the_verifier_model_corrected_path():
    cat = _catalog()
    client = ScriptedFakeLlmClient([_violation_json(), "korrigiert.", _CLEAN])
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client, cat),
            _generator(client, "gpt-5.1"),
            cat,
            "Frage?",
            Answer(text="Falscher Entwurf.", model="gpt-5.1"),
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.CORRECTED
    assert answer.model == "gpt-5.1"  # the REGENERATED answer carries L1's model
    assert answer.model != "mistral-small-2603"


def test_final_answer_model_is_never_the_verifier_model_hedge_path():
    cat = _catalog()
    client = ScriptedFakeLlmClient(
        [_violation_json(), "immer noch falsch", _violation_json()]
    )
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client, cat),
            _generator(client, "gpt-5.1"),
            cat,
            "Frage?",
            Answer(text="Falscher Entwurf.", model="gpt-5.1"),
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    assert (
        answer.model == "l3-hedge"
    )  # the deterministic sentinel — never the verifier model string
    assert answer.model != "mistral-small-2603"
