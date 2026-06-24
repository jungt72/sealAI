from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import (
    Answer,
    Flags,
    GroundingFact,
    ModelConfig,
    VerifierAction,
    VerifierFinding,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import (
    L3Verifier,
    build_correction_note,
    build_hedge,
    build_matrix_hedge,
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


def test_verify_unparseable_twice_fails_closed_to_hedge():
    # P0.1: the LLM verdict IS the catalog/matrix trap net. If it does not parse (and the single retry
    # also fails), that net never ran — the draft is UNVERIFIED, so run_verify must fail CLOSED to a
    # hedge, never PASS the unverified draft through. (Regression for the §2/§9 fail-open.)
    client = ScriptedFakeLlmClient(["not json at all", "still not json"])
    draft = _draft("eine saubere Antwort ohne Zahlen")
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
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    assert verdict.parse_ok is False
    assert answer is not draft  # the unverified draft was NOT shipped
    assert answer.model == "l3-hedge"
    assert len(client.calls) == 2  # verify + one retry, no regeneration


def test_verify_unparseable_then_clean_retry_passes():
    # P0.1: a TRANSIENT unparseable verdict recovers on the single retry → normal PASS, no over-hedging.
    client = ScriptedFakeLlmClient(["not json at all", _CLEAN])
    draft = _draft("eine saubere Antwort ohne Zahlen")
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
    assert answer is draft  # recovered → untouched
    assert len(client.calls) == 2  # verify + retry, then clean


def test_run_parametric_guard_passes_clean_draft():
    # P0.3: no kern-quantity assertion → clean passthrough, no verdict (and no LLM at all).
    from sealai_v2.core.l3_verifier import run_parametric_guard

    draft = _draft("Eine Orientierung ohne Kern-Zahlen.")
    answer, verdict = run_parametric_guard(draft)
    assert answer is draft and verdict is None


def test_run_parametric_guard_hedges_a_parametric_leak_without_l3():
    # P0.3: the DETERMINISTIC parametric Schranke must fire even with NO LLM verifier (kill-switch /
    # unconfigured) — a draft asserting a kern-quantity is hedged, never shipped.
    from sealai_v2.core.l3_verifier import run_parametric_guard

    draft = _draft("Die Umfangsgeschwindigkeit liegt bei 10,47 m/s.")
    answer, verdict = run_parametric_guard(draft)
    assert verdict is not None and verdict.action == VerifierAction.BLOCKED_HEDGE
    assert answer.model == "l3-hedge"
    assert answer is not draft


def test_verify_does_not_deterministically_hedge_equivalence_claims():
    # §9.2 DESIGN LOCK: run_verify has NO deterministic text-matcher for affirmative interchangeability
    # ("Teil X = Teil Y"). A regex guard over-fired on benign echoes and alternatives questions (eval
    # v21-qdrant-gate*: APP-01 and ALT-NEUTRAL-EMPTY-01 were good answers wrongly hedged), so §9.2 is
    # held by the L1 prompt (DEC-AEQUIVALENZ passes) plus the deploy-blocking DEC-AEQUIVALENZ hard gate.
    # An affirmative "1:1 austauschbar" draft must therefore reach the LLM verify path (here scripted
    # clean → PASS), never be short-circuited into a regex hedge. Re-adding such a guard fails this test.
    client = ScriptedFakeLlmClient([_CLEAN])
    draft = _draft("Ja, die beiden O-Ringe sind 1:1 austauschbar.")
    answer, verdict = asyncio.run(
        run_verify(
            _verifier(client),
            _generator(client),
            _catalog(),
            "Kann ich tauschen?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.PASS  # no deterministic §9.2 short-circuit
    assert answer is draft
    assert len(client.calls) == 1  # LLM verify ran, no regex short-circuit


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


def test_reviewed_violation_that_persists_hedges_with_correct_fact_not_wrong_claim():
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
    # the hedge STATES the reviewed correct fact (owner-grounded) + the verify caveat ...
    assert "unpolar" in answer.text.lower()
    assert "verifizieren" in answer.text.lower()
    # ... and NEVER echoes the flagged wrong claim / evidence (output integrity)
    assert "Zitat" not in answer.text
    assert "immer noch polar" not in answer.text
    # the gate's polar-heuristic must NOT false-fire on the clean hedge
    from sealai_v2.eval.report import _asserts_epdm_polar

    assert _asserts_epdm_polar(answer.text) is False


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
    assert (
        "EPDM polar" not in h
    )  # no catalog → generic hedge, never echoes the flagged claim


def test_hedge_states_reviewed_correct_fact_not_the_wrong_claim():
    # with the catalog, the hedge asserts the reviewed CORRECT fact (R1.correct) + caveat,
    # and never the flagged wrong-claim evidence
    h = build_hedge(
        (VerifierFinding("R1", "confident_wrong", "reviewed", "EPDM ist polar"),),
        _catalog(),
    )
    assert "UNPOLAR".lower() in h.lower()  # the reviewed correct fact
    assert "verifizieren" in h.lower()
    assert "EPDM ist polar" not in h  # never the wrong claim/evidence


def test_user_facing_hedges_carry_no_l3_internals():
    """kern-fix-01: a user-facing hedge must read as a clean orientation — never expose the internal
    verifier ('L3' / 'Verifikation' / 'Falle … markiert'). The safety framing (Vorsicht + verifizieren
    + keine Freigabe) stays. Covers both build_hedge branches and the matrix hedge."""
    internals = ("L3", "Verifikation", "Falle")
    finding = VerifierFinding("R1", "confident_wrong", "reviewed", "EPDM ist polar")

    with_facts = build_hedge((finding,), _catalog())
    generic = build_hedge((finding,))  # no catalog → generic branch
    matrix = build_matrix_hedge(
        (
            GroundingFact(
                text="EPDM ist mit Mineralöl unverträglich",
                quelle="Matrix §4",
                card_id="C1",
            ),
        ),
        (VerifierFinding("C1", "confident_wrong", "reviewed", "x", kind="matrix"),),
    )
    for h in (with_facts, generic, matrix):
        for token in internals:
            assert token not in h, f"hedge leaks internal token {token!r}: {h!r}"
        assert "Vorsicht" in h  # keep the user-facing safety framing
        assert "verifizieren" in h.lower()


def test_gate_polar_heuristic_ignores_hedge_answer():
    from sealai_v2.eval.report import _final_answer_asserts_epdm_polar

    # a deterministic hedge never ASSERTS the wrong claim, even if it mentions the word
    hedge_rec = {
        "answer_model": "l3-hedge",
        "answer_text": "... EPDM ist ein polarer Kautschuk ...",
    }
    assert _final_answer_asserts_epdm_polar(hedge_rec) is False
    # a real model answer that asserts polar is still flagged
    real_rec = {
        "answer_model": "gpt-5.1",
        "answer_text": "EPDM ist ein polarer Kautschuk.",
    }
    assert _final_answer_asserts_epdm_polar(real_rec) is True


def _gate_rec(case_id, column, answer, *, grounded=False, action="pass"):
    return {
        "case_id": case_id,
        "column": column,
        "answer_text": answer,
        "answer_model": "gpt-5.1",
        "grounded": grounded,
        "verifier": {
            "action": action,
            "findings": [],
            "regenerated": action == "corrected",
        },
        "score": {"provisional_gate_clean": True},
    }


def _calc_ok():
    return [
        _gate_rec("CALC-02", c, "Bereiche, gegen Datenblatt verifizieren.")
        for c in ("flags_off", "flags_on")
    ]


def test_gate_trap02_avoided_at_l1_is_pass():
    from sealai_v2.eval.report import _render_l3_section

    recs = [
        _gate_rec(
            "TRAP-02",
            "flags_off",
            "EPDM ist unpolar; NBR/FKM nehmen.",
            grounded=True,
            action="pass",
        ),
        _gate_rec(
            "TRAP-02", "flags_on", "EPDM ist unpolar.", grounded=True, action="pass"
        ),
        *_calc_ok(),
    ]
    text = "\n".join(_render_l3_section({}, recs))
    assert "avoided at L1 (grounded)" in text
    assert "✅ signal-pass" in text  # outcome-defined: avoided counts as success
    assert "Outcome signal = ✅" in text


def test_gate_trap02_polar_final_still_fails():
    from sealai_v2.eval.report import _render_l3_section

    recs = [
        _gate_rec(
            "TRAP-02",
            "flags_off",
            "EPDM ist ein polarer Kautschuk.",
            grounded=True,
            action="pass",
        ),
        _gate_rec(
            "TRAP-02", "flags_on", "EPDM ist unpolar.", grounded=True, action="pass"
        ),
        *_calc_ok(),
    ]
    text = "\n".join(_render_l3_section({}, recs))
    assert "ASSERTS POLAR" in text
    assert "❌ signal-FAIL" in text


def test_asserts_epdm_polar_ignores_polar_media_usage():
    from sealai_v2.eval.report import _asserts_epdm_polar

    # correct usages → NOT flagged (measurement hygiene)
    assert (
        _asserts_epdm_polar(
            "EPDM ist ein unpolarer Kautschuk und quillt in unpolaren Ölen."
        )
        is False
    )
    assert (
        _asserts_epdm_polar("EPDM ist für polare Medien wie Wasser/Glykol geeignet.")
        is False
    )
    assert (
        _asserts_epdm_polar("EPDM ist für **polare Medien** wie Wasser.") is False
    )  # markdown-bold robust
    assert (
        _asserts_epdm_polar(
            "EPDM ist gut gegen polare Lösungsmittel, quillt aber in Öl."
        )
        is False
    )
    assert _asserts_epdm_polar("Aceton ist ein polares Lösungsmittel.") is False
    # a real assertion that EPDM itself is polar → still flagged
    assert _asserts_epdm_polar("EPDM ist ein polarer Kautschuk.") is True
    assert _asserts_epdm_polar("Weil EPDM polar ist, quillt es in Öl.") is True


# --- L3 precision over-application fix (PREC-EINZELZAHL / PREC-LEBENSDAUER firing condition) ---
# A range-precision trap must NOT fire when the answer ALREADY gives the quantity as a range WITH
# a verify/Datenblatt caveat (respect the catalog's "Einzelzahl OHNE Bereich" scope); a bare
# single value must STILL fire (catch preserved). These are the executable gate for the fix.

_PREC = TrapEntry(
    id="PREC-EINZELZAHL",
    trigger="exakte Einzelzahl ohne Bereich",
    wrong=("falsch-präzise Einzelzahl ohne Bereich/Vorbehalt",),
    correct="Compound-abhängige Größen als Bereich angeben und gegen Datenblatt verifizieren.",
    gates=("invented_precision",),
    provenance=("eval:UNCERT-01",),
    review_state="reviewed",
)


def _prec_catalog() -> TrapCatalog:
    return TrapCatalog(entries=(_PREC,))


def _prec_verifier(client) -> L3Verifier:
    return L3Verifier(
        client, VerifierPromptAssembler(), ModelConfig("fake-l3"), _prec_catalog()
    )


def _prec_violation(evidence: str, trap_id: str = "PREC-EINZELZAHL") -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "trap_id": trap_id,
                    "gate": "invented_precision",
                    "violated": True,
                    "evidence": evidence,
                }
            ],
            "verdict": "violation",
        }
    )


def test_precision_overapplication_suppressed_when_range_and_caveat():
    # the documented false-flag: TRAP-01 flags_off — a range + verify/Datenblatt caveat
    ev = (
        "Viele FKM-Compounds fangen schon ab ca. 120–130 °C im Dampf an abzubauen "
        "(typisch – bitte gegen das Datenblatt des konkreten Compounds verifizieren)."
    )
    client = ScriptedFakeLlmClient([_prec_violation(ev)])
    raw = asyncio.run(_prec_verifier(client).verify("Frage?", "Entwurf"))
    assert (
        raw.findings == ()
    )  # range + caveat → not invented precision → L3 over-applied → dropped


def test_precision_still_fires_on_bare_single_value():
    ev = "~25 % Verpressung als Zielwert ansetzen."  # single value, no range
    client = ScriptedFakeLlmClient([_prec_violation(ev)])
    raw = asyncio.run(_prec_verifier(client).verify("Frage?", "Entwurf"))
    assert len(raw.findings) == 1 and raw.findings[0].trap_id == "PREC-EINZELZAHL"


def test_precision_requires_both_range_and_caveat():
    # range but NO caveat → still fires
    c1 = ScriptedFakeLlmClient([_prec_violation("Verpressung 15–25 %.")])
    assert len(asyncio.run(_prec_verifier(c1).verify("F", "E")).findings) == 1
    # caveat but NO range (a fabricated single value) → still fires
    c2 = ScriptedFakeLlmClient(
        [_prec_violation("genau 178 °C (gegen Datenblatt verifizieren).")]
    )
    assert len(asyncio.run(_prec_verifier(c2).verify("F", "E")).findings) == 1


def test_precision_overapplication_yields_pass_no_regen():
    ev = "Statischer O-Ring: typisch 15–25 % Verpressung (gegen Datenblatt verifizieren)."
    client = ScriptedFakeLlmClient([_prec_violation(ev)])
    draft = _draft(ev)
    answer, verdict = asyncio.run(
        run_verify(
            _prec_verifier(client),
            _generator(client),
            _prec_catalog(),
            "Frage?",
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.PASS
    assert answer is draft  # not blocked, not regenerated
    assert len(client.calls) == 1  # only the verify call


def test_is_precision_overapplication_predicate():
    from sealai_v2.core.l3_verifier import is_precision_overapplication as ov

    assert ov(
        "PREC-EINZELZAHL", "ca. 120–130 °C (typisch, gegen Datenblatt verifizieren)"
    )
    # OPTIMIZE_BACKLOG #6 — a lifetime/future-performance range is NOT the correct form (no
    # quantitative prediction, not even a hedged range) → NOT exempt; L3 catches it.
    assert not ov(
        "PREC-LEBENSDAUER", "5 000–20 000 Betriebsstunden (typisch, Richtwert)"
    )
    assert not ov("PREC-EINZELZAHL", "genau 178 °C")  # no range, no caveat
    assert not ov("PREC-EINZELZAHL", "15–25 %")  # range but no caveat
    assert not ov(
        "PREC-COMPOUND-NUMMER", "FKM 70 (typisch, Datenblatt 1–2)"
    )  # not a range-trap
    assert not ov(
        "TRAP-FKM-DAMPF", "120–130 °C typisch Datenblatt"
    )  # not a precision trap


def test_precision_overapplication_bis_and_ellipsis_ranges():
    from sealai_v2.core.l3_verifier import is_precision_overapplication as ov

    assert ov(
        "PREC-EINZELZAHL",
        "Standard liegt im Bereich +135 bis +150 °C (typisch, Datenblatt)",
    )
    assert ov("PREC-EINZELZAHL", "ca. 120…150 °C (typisch – Datenblatt verifizieren)")
    assert ov("PREC-EINZELZAHL", "5.000 bis 20.000 h (Richtwert, Datenblatt)")


def test_precision_overapplication_checks_draft_not_just_evidence():
    from sealai_v2.core.l3_verifier import is_precision_overapplication as ov

    # evidence is a bare value, but the DRAFT presents the quantity as a range + caveat → suppress
    assert ov(
        "PREC-EINZELZAHL",
        "liegt bei 145 °C",
        "Sattdampf: typisch ca. 140–160 °C, gegen Datenblatt verifizieren.",
    )
    # nothing range/caveat anywhere → still fires
    assert not ov("PREC-EINZELZAHL", "genau 178 °C", "Die Grenze ist genau 178 °C.")


def test_precision_draft_check_via_verify():
    # mirrors UNCERT-01 flags_off: verifier quotes a "bis"-range snippet without the caveat word,
    # but the DRAFT is a proper range + caveat answer → L3 over-applied → suppressed
    ev = "Standard-EPDM liegt eher bei +135 bis +150 °C in Dampf."
    draft = (
        "Typisch ca. 140–160 °C (typisch – Datenblatt des Herstellers verifizieren)."
    )
    client = ScriptedFakeLlmClient([_prec_violation(ev)])
    raw = asyncio.run(_prec_verifier(client).verify("Frage?", draft))
    assert raw.findings == ()


# --- OPTIMIZE_BACKLOG #5: topic-scoped correction ("reviewed ≠ topically appropriate") -----------
# Built against the REAL catalog: a material-recommending reviewed trap injects its topic-AGNOSTIC
# `correct_general` always, but its topic-SCOPED `correct_recommendation` ONLY when the question matches
# `applies_to`. Floor is deterministic (pure builders + scripted fake client; no live LLM).
from sealai_v2.knowledge.traps import load_traps as _load_traps  # noqa: E402

_REAL = _load_traps()
_ACETONE_Q = (
    "Ich brauche eine Dichtung, die gegen Aceton beständig ist, dauerhaft 180 °C "
    "aushält und möglichst günstig ist."
)
_OIL_Q = "Unsere EPDM-Wellendichtung quillt in unserem Hydrauliköl — woran liegt das?"
_DEFAULT01_Q = (
    "Wir verbauen seit Jahren NBR an allen unseren Getrieben. Jetzt haben wir ein neues "
    "Getriebe mit Synthetiköl bei 130 °C Dauertemperatur. NBR wie immer?"
)


def _epdm_finding() -> VerifierFinding:
    return VerifierFinding(
        "TRAP-EPDM-MINERALOEL",
        "confident_wrong",
        "reviewed",
        "EPDM ist ein polarer Kautschuk",
    )


def _real_verifier(client) -> L3Verifier:
    return L3Verifier(client, VerifierPromptAssembler(), ModelConfig("fake-l3"), _REAL)


def _real_generator(client) -> L1Generator:
    return L1Generator(client, PromptAssembler(), ModelConfig("fake-l1"))


def test_topic_scope_pure_acetone_general_only_no_oil_rec():
    # an EPDM-MINERALOEL finding on an ACETONE question: general (polarity) injected, oil rec suppressed
    note = build_correction_note(_REAL, (_epdm_finding(),), question=_ACETONE_Q)
    hedge = build_hedge((_epdm_finding(),), _REAL, question=_ACETONE_Q)
    for out in (note, hedge):
        assert out is not None
        assert (
            "unpolar" in out.lower()
        )  # the topic-agnostic correction IS present (polarity fixed)
        # the topic-scoped material recommendation (acetone-unsuitable!) is NOT injected
        assert "Mineralöl-Hydraulik" not in out
        assert "NBR" not in out and "FKM" not in out


def test_topic_scope_e2e_acetone_hedge_no_oil_recommendation():
    # "EPDM polar" draft on the acetone question → regen note + BLOCKED_HEDGE carry no acetone-unsuitable
    # material; polarity still corrected. (Scripted: verify→regen→verify-persists → hedge.)
    client = ScriptedFakeLlmClient(
        [
            _violation("TRAP-EPDM-MINERALOEL", "confident_wrong"),
            "Eine überarbeitete Antwort.",
            _violation("TRAP-EPDM-MINERALOEL", "confident_wrong"),
        ]
    )
    draft = Answer(
        text="EPDM ist ein polarer Kautschuk; für Aceton bei 180 °C nimm einfach EPDM.",
        model="fake-l1",
    )
    answer, verdict = asyncio.run(
        run_verify(
            _real_verifier(client),
            _real_generator(client),
            _REAL,
            _ACETONE_Q,
            draft,
            flags=Flags(),
        )
    )
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    # Assert on the DETERMINISTIC user-facing hedge (the bug surface), not the assembled regen prompt:
    # the L1 system prompt legitimately lists material names in its static trap-examples, so it is not a
    # clean substrate. The scoped correction-NOTE content is asserted in the pure-function test above.
    assert "unpolar" in answer.text.lower()  # polarity still corrected (general fact)
    assert (
        "NBR" not in answer.text and "FKM" not in answer.text
    )  # no acetone-unsuitable material


def test_topic_scope_home_topic_mineraloil_keeps_recommendation():
    # NO-REGRESSION: on a mineral-oil question the oil recommendation IS injected (scopes, not strips)
    note = build_correction_note(_REAL, (_epdm_finding(),), question=_OIL_Q)
    hedge = build_hedge((_epdm_finding(),), _REAL, question=_OIL_Q)
    for out in (note, hedge):
        assert "unpolar" in out.lower()
        assert "NBR" in out and "FKM" in out  # topic matches → recommendation present


def test_topic_scope_home_topic_default01_nbr_dauertemp_keeps_recommendation():
    # O3 semantic-token gate end-to-end: DEFAULT-01's real question fires NBR-DAUERTEMP's recommendation
    nbr = VerifierFinding(
        "TRAP-NBR-DAUERTEMP", "confident_wrong", "reviewed", "NBR wie immer"
    )
    note = build_correction_note(_REAL, (nbr,), question=_DEFAULT01_Q)
    assert "HNBR" in note and "FKM" in note


def test_recommendation_applies_unit_table():
    from sealai_v2.core.l3_verifier import _recommendation_applies as applies

    epdm = _REAL.by_id("TRAP-EPDM-MINERALOEL")
    nbr = _REAL.by_id("TRAP-NBR-DAUERTEMP")
    prec = _REAL.by_id("PREC-EINZELZAHL")  # unsplit → empty applies_to
    assert applies(epdm, _ACETONE_Q, None) is False  # acetone → suppress
    assert applies(epdm, "EPDM quillt in meinem Hydrauliköl", None) is True
    assert applies(epdm, "EPDM in Mineralöl bei 80 °C", None) is True
    assert (
        applies(epdm, "Dichtung in Schmieröl", None) is False
    )  # synonym miss (conservative)
    assert applies(prec, "egal was", None) is False  # empty applies_to → never
    assert applies(nbr, _DEFAULT01_Q, None) is True
    assert (
        applies(nbr, "Die Grenze liegt bei 130 °C", None) is False
    )  # O3: bare '130' is not a tag


def test_topic_scope_unsplit_trap_unchanged():
    # an unsplit reviewed trap still injects its whole `correct` (fallback), regardless of question
    leck = _REAL.by_id("CONF-PAUSCHAL-BESTAENDIG")  # method trap, no split
    assert not leck.has_split
    f = VerifierFinding(leck.id, "confident_wrong", "reviewed", "pauschal ja")
    note = build_correction_note(_REAL, (f,), question="irgendeine Frage")
    assert leck.correct[:30] in note  # full correct injected unchanged


def test_recommends_topic_unsuitable_material_detector():
    from sealai_v2.eval.report import _recommends_topic_unsuitable_material as flag

    # a final that RECOMMENDS an acetone-unsuitable material → flagged
    assert flag("Für Aceton bei 180 °C nimm NBR oder FKM.", "CONFLICT-01") is True
    # a correct NEGATIVE statement (the material is attacked) → NOT flagged
    assert (
        flag("Aceton greift NBR und FKM an; nimm stattdessen EPDM/FFKM.", "CONFLICT-01")
        is False
    )
    # a deterministic l3-hedge is skipped at the gate wrapper
    from sealai_v2.eval.report import _final_answer_recommends_unsuitable as gate

    assert (
        gate(
            {
                "case_id": "CONFLICT-01",
                "answer_model": "l3-hedge",
                "answer_text": "nimm NBR",
            }
        )
        is False
    )
    # a case not in the reviewed map → never flagged
    assert flag("nimm NBR", "TRAP-02") is False
    # live-eval-surfaced false positives (fix-5-l3-topic-scope REPLAY), now regression-locked:
    # FFKM ⊅ FKM and HNBR ⊅ NBR — FFKM/HNBR are the SUITABLE recs, not the attacked materials
    assert (
        flag("Für Aceton FFKM nehmen; FFKM ist die sichere Wahl.", "CONFLICT-01")
        is False
    )
    # a markdown-bolded negation ('**nicht** geeignet') must still guard the 'geeignet' recommend-token
    assert (
        flag(
            "**Standard-Elastomere (NBR, EPDM, FKM, VMQ)** → für Aceton **nicht** geeignet.",
            "CONFLICT-01",
        )
        is False
    )
    # a genuine misdirection ('NBR ist geeignet', no negation) is still caught
    assert flag("Für Aceton ist NBR gut geeignet.", "CONFLICT-01") is True
