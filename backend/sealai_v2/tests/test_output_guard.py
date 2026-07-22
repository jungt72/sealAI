"""INC-NARRATOR-CONTRACT Phase 3 — claim-level output_guard truth table.

Validates the fail-closed enforcement over real contracts (built by build_contract) + crafted renders:
clean render passes; each defect (invented number/material, missing clause, forbidden phrase, foreign
technical sentence) fail-closes; user-stated values + linguistic transitions + clarification questions
pass. The guard is PURE/INERT — this tests the enforcement logic, not any prod behaviour.
"""

import pytest

from sealai_v2.core.coverage import coverage_for
from sealai_v2.core.contracts import GroundingFact
from sealai_v2.core.output_guard import correction_note, evaluate_render
from sealai_v2.core.response_contract import build_contract, build_guard_contract

V_DISQ = {
    "disqualified": True,
    "reason": "FKM/Heißdampf unverträglich",
    "source": "MX-FKM-DAMPF",
}
V_NO_MEDIUM = {"disqualified": False, "basis": "no_medium"}

_FACT = GroundingFact(
    text="FKM gegen Heißdampf: unverträglich (Hydrolyse); EPDM ist der Dampf-Standard.",
    quelle="Verträglichkeitsmatrix",
    card_id="MX-FKM-DAMPF",
    kind="matrix",
)

C_DISQ = build_contract(
    coverage=coverage_for(V_DISQ, None),
    grounding_facts=(_FACT,),
    gegencheck_verdict=V_DISQ,
    calc=None,
).to_dict()

# A clean render: restates the grounded claim, names only allowed materials, includes the required
# clause, invents no number, uses no forbidden phrase.
CLEAN = (
    "FKM ist gegen Heißdampf nicht beständig, da es zur Hydrolyse kommt. "
    "EPDM ist hier der Dampf-Standard. "
    "Die finale Compound-/Werkstofffreigabe trifft der Hersteller."
)


def _kinds(answer, contract=C_DISQ, **kw):
    return {
        v.kind
        for v in evaluate_render(answer_text=answer, contract=contract, **kw).violations
    }


def test_clean_render_passes():
    r = evaluate_render(answer_text=CLEAN, contract=C_DISQ)
    assert r.ok and r.action == "PASS", r.to_dict()


def test_invented_number_blocks():
    r = evaluate_render(
        answer_text=CLEAN + " Dauerhaft sind etwa 120 °C möglich.", contract=C_DISQ
    )
    assert not r.ok and r.action == "BLOCK"
    assert "invented_number" in {v.kind for v in r.violations}


def test_user_stated_value_is_not_invented():
    a = "Bei den genannten 140 °C bleibt FKM unbeständig gegen Heißdampf."
    assert "invented_number" in _kinds(a)  # without known_values -> flagged
    assert "invented_number" not in _kinds(
        a, known_values=("140",)
    )  # echoing the user -> ok


def test_invented_material_blocks():
    assert "invented_material" in _kinds(CLEAN + " NBR ist eine günstige Alternative.")


def test_missing_required_clause_blocks():
    two_sentences = (
        "FKM ist gegen Heißdampf nicht beständig. EPDM ist der Dampf-Standard."
    )
    assert "missing_required_clause" in _kinds(two_sentences)


def test_forbidden_phrase_blocks():
    assert "forbidden_phrase" in _kinds(CLEAN + " Das ist ein belegter Befund.")


def test_foreign_technical_sentence_blocks():
    foreign = (
        " Für aggressive Laugen ist die Chemikalienbeständigkeit hier ausgezeichnet."
    )
    assert "unmapped_sentence" in _kinds(CLEAN + foreign)


def test_allowed_material_name_alone_does_not_cover_an_unrelated_claim():
    answer = (
        "FKM ist in konzentrierter Salpetersäure dauerhaft beständig. "
        "Die finale Compound-/Werkstofffreigabe trifft der Hersteller."
    )
    result = evaluate_render(answer_text=answer, contract=C_DISQ)
    assert result.action == "BLOCK"
    assert "unmapped_sentence" in {v.kind for v in result.violations}


def test_clean_render_records_sentence_to_claim_bindings():
    result = evaluate_render(answer_text=CLEAN, contract=C_DISQ)
    assert result.to_dict()["claim_mappings"] == [
        {"sentence_index": 0, "claim_id": "MX-FKM-DAMPF"},
        {"sentence_index": 1, "claim_id": "MX-FKM-DAMPF"},
    ]


def _atomic_contract(claim_id: str, text: str, material: str) -> dict:
    return {
        "status": "COVERED_RECOMMENDATION",
        "allowed_claims": [{"id": claim_id, "text": text}],
        "required_clauses": [
            "Die finale Compound-/Werkstofffreigabe trifft der Hersteller."
        ],
        "missing_fields": [],
        "allowed_materials": [material],
        "allowed_values": [],
        "forbidden_phrases": [],
    }


_FKM_DAMPF_CONTRACT = _atomic_contract(
    "MX-FKM-DAMPF",
    "FKM hydrolysiert und versprödet in Sattdampf/Heißdampf — die hohe "
    "Temperaturbeständigkeit in Öl überträgt sich nicht auf Dampf.",
    "FKM",
)
_EPDM_DAMPF_CONTRACT = _atomic_contract(
    "MX-EPDM-DAMPF",
    "EPDM (peroxidvernetzt) ist gegen Dampf-/SIP-Anwendungen beständig "
    "(der etablierte Dampf-/SIP-Standardwerkstoff).",
    "EPDM",
)
_NBR_SYNTHETIKOEL_CONTRACT = _atomic_contract(
    "MX-NBR-SYN",
    "NBR gegen Synthetiköl: bedingt — abhängig vom Estergehalt; vor Einsatz prüfen.",
    "NBR",
)
_FINAL_RELEASE = " Die finale Compound-/Werkstofffreigabe trifft der Hersteller."


@pytest.mark.parametrize(
    "answer",
    (
        "FKM hydrolysiert nicht in Heißdampf.",
        "FKM ist in Heißdampf nicht unverträglich.",
    ),
)
def test_negated_negative_predicate_cannot_bind_to_negative_claim(answer):
    result = evaluate_render(
        answer_text=answer + _FINAL_RELEASE,
        contract=_FKM_DAMPF_CONTRACT,
    )
    assert result.action == "BLOCK"
    assert result.claim_mappings == ()


@pytest.mark.parametrize(
    "answer",
    (
        "EPDM scheitert in Dampf-/SIP-Anwendungen.",
        "EPDM ist gegen Dampf-/SIP-Anwendungen vollkommen wirkungslos.",
        "EPDM ist ein untauglicher Dampf-/SIP-Standardwerkstoff.",
        "EPDM ist kein Dampf-/SIP-Standardwerkstoff.",
        "EPDM ist keinesfalls gegen Dampf-/SIP-Anwendungen beständig.",
        "EPDM ist niemals gegen Dampf-/SIP-Anwendungen beständig.",
        "EPDM ist nie gegen Dampf-/SIP-Anwendungen beständig.",
        "EPDM ist auf keinen Fall gegen Dampf-/SIP-Anwendungen beständig.",
        "EPDM ist unter keinen Umständen gegen Dampf-/SIP-Anwendungen beständig.",
    ),
)
def test_negative_or_negated_standard_cannot_bind_to_positive_claim(answer):
    result = evaluate_render(
        answer_text=answer + _FINAL_RELEASE,
        contract=_EPDM_DAMPF_CONTRACT,
    )
    assert result.action == "BLOCK"
    assert result.claim_mappings == ()


@pytest.mark.parametrize(
    "answer",
    (
        "FKM hydrolysiert niemals in Heißdampf.",
        "FKM hydrolysiert in Heißdampf keinesfalls.",
    ),
)
def test_adverbially_negated_negative_predicate_is_positive_and_cannot_bind(answer):
    result = evaluate_render(
        answer_text=answer + _FINAL_RELEASE,
        contract=_FKM_DAMPF_CONTRACT,
    )
    assert result.action == "BLOCK"
    assert result.claim_mappings == ()


def test_unlicensed_exclusivity_cannot_bind_to_nonexclusive_claim():
    result = evaluate_render(
        answer_text="EPDM ist der einzige Dampf-/SIP-Standardwerkstoff."
        + _FINAL_RELEASE,
        contract=_EPDM_DAMPF_CONTRACT,
    )
    assert result.action == "BLOCK"
    assert result.claim_mappings == ()


def test_atomic_positive_standard_paraphrase_still_binds():
    result = evaluate_render(
        answer_text=(
            "EPDM ist für Dampf-/SIP-Anwendungen beständig und der etablierte Standardwerkstoff."
            + _FINAL_RELEASE
        ),
        contract=_EPDM_DAMPF_CONTRACT,
    )
    assert result.action == "PASS", result.to_dict()
    assert result.to_dict()["claim_mappings"] == [
        {"sentence_index": 0, "claim_id": "MX-EPDM-DAMPF"}
    ]


def test_conditional_claim_cannot_be_promoted_to_unconditional():
    conditional = evaluate_render(
        answer_text=(
            "NBR gegen Synthetiköl ist nur bedingt beständig — es hängt vom Estergehalt ab "
            "und sollte vor dem Einsatz geprüft werden." + _FINAL_RELEASE
        ),
        contract=_NBR_SYNTHETIKOEL_CONTRACT,
    )
    assert conditional.action == "PASS", conditional.to_dict()

    unconditional = evaluate_render(
        answer_text="NBR ist gegen Synthetiköl beständig." + _FINAL_RELEASE,
        contract=_NBR_SYNTHETIKOEL_CONTRACT,
    )
    assert unconditional.action == "BLOCK"
    assert unconditional.claim_mappings == ()


def test_linguistic_transition_passes():
    r = evaluate_render(
        answer_text="Gerne gehe ich das mit dir durch. " + CLEAN, contract=C_DISQ
    )
    assert r.ok, r.to_dict()


def test_clarification_question_passes():
    c = build_contract(
        coverage=coverage_for(V_NO_MEDIUM, None),
        grounding_facts=(),
        gegencheck_verdict=V_NO_MEDIUM,
        calc=None,
    ).to_dict()
    answer = (
        "Ohne das Medium ist keine belastbare Auslegung möglich — bitte ergänzen. "
        "Welches Medium liegt an?"
    )
    r = evaluate_render(answer_text=answer, contract=c)
    assert r.ok, r.to_dict()


def test_forbidden_phrase_inside_an_allowed_claim_is_not_flagged():
    # if a grounded claim legitimately contains a word that is otherwise forbidden, restating it is ok
    c = {
        "status": "COVERED_RECOMMENDATION",
        "allowed_claims": [
            {
                "id": "X",
                "text": "Der typische Dauereinsatz liegt im Öl.",
                "severity": "info",
                "sources": [],
                "kind": "card",
            }
        ],
        "required_clauses": [],
        "missing_fields": [],
        "allowed_materials": [],
        "allowed_values": [],
        "forbidden_phrases": ["typisch", "belegt"],
        "coverage_status": "in_envelope",
    }
    assert "forbidden_phrase" not in _kinds(
        "Der typische Dauereinsatz liegt im Öl.", contract=c
    )


def test_block_action_and_to_dict_shape():
    r = evaluate_render(answer_text="EPDM ist bis 200 °C beständig.", contract=C_DISQ)
    d = r.to_dict()
    assert d["action"] == "BLOCK" and d["ok"] is False
    assert isinstance(d["violations"], list) and d["violations"]


# ── check_sentence_coverage=False (P0-B: the guard-only / general-knowledge path) ───────────────────

# "was ist FKM?"-shaped grounding: an FKM Fachkarte, no verdict, no matrix cell.
_FKM_KNOWLEDGE_FACT = GroundingFact(
    text="FKM ist ein fluoriertes Elastomer mit hoher Temperatur- und Ölbeständigkeit.",
    quelle="Fachkarte FKM",
    card_id="CARD-FKM-1",
    kind="card",
)
C_GENERAL = build_guard_contract(
    grounding_facts=(_FKM_KNOWLEDGE_FACT,), calc=None
).to_dict()


def test_default_check_sentence_coverage_is_unchanged_for_every_existing_caller():
    # the default (omitted) must reproduce EXACTLY today's behaviour — the Gegencheck-path
    # foreign-sentence BLOCK from test_foreign_technical_sentence_blocks, byte-identical.
    foreign = (
        " Für aggressive Laugen ist die Chemikalienbeständigkeit hier ausgezeichnet."
    )
    with_default = evaluate_render(answer_text=CLEAN + foreign, contract=C_DISQ)
    with_explicit_true = evaluate_render(
        answer_text=CLEAN + foreign, contract=C_DISQ, check_sentence_coverage=True
    )
    assert with_default.to_dict() == with_explicit_true.to_dict()
    assert "unmapped_sentence" in {v.kind for v in with_default.violations}


def test_light_mode_does_not_block_in_depth_elaboration_beyond_the_literal_claim():
    # this is the WHOLE POINT of the light mode: a knowledge answer legitimately goes further than
    # the one retrieved claim sentence ("gib das volle Bild, nicht die Kurzfassung") — with
    # check_sentence_coverage=False this must NOT be flagged as an unmapped/foreign sentence, even
    # though it names no contract material/clause verbatim and would fail the full-mode check.
    # (NOT a sentence naming FKM — the guard already exempts ANY sentence anchored to an allowed
    # material from the coverage check in BOTH modes, see prefilter comment "(1) anchored to a
    # contract/known material — elaboration is allowed"; that exemption is pre-existing, unrelated
    # to P0-B. This test targets what check_sentence_coverage actually gates: a genuinely
    # foreign-subject technical sentence, same shape as test_foreign_technical_sentence_blocks.)
    elaboration = (
        "Für aggressive Laugen ist die Chemikalienbeständigkeit hier ausgezeichnet."
    )
    full = evaluate_render(
        answer_text=elaboration, contract=C_GENERAL, check_sentence_coverage=True
    )
    light = evaluate_render(
        answer_text=elaboration, contract=C_GENERAL, check_sentence_coverage=False
    )
    assert "unmapped_sentence" in {
        v.kind for v in full.violations
    }  # full mode: would block
    assert light.ok and light.action == "PASS"  # light mode: elaboration is allowed


def test_light_mode_still_blocks_a_close_semantic_inversion():
    result = evaluate_render(
        answer_text="FKM ist gegenüber Öl nicht beständig.",
        contract=C_GENERAL,
        check_sentence_coverage=False,
    )
    assert result.action == "BLOCK"
    assert "semantic_inversion" in {v.kind for v in result.violations}
    assert "belegten Richtung" in correction_note(result)


def test_light_mode_does_not_promote_a_conditional_claim_to_unconditional():
    result = evaluate_render(
        answer_text="NBR ist gegen Synthetiköl beständig.",
        contract=_NBR_SYNTHETIKOEL_CONTRACT,
        check_sentence_coverage=False,
    )
    assert result.action == "BLOCK"
    assert "semantic_inversion" in {v.kind for v in result.violations}


def test_light_mode_still_blocks_invented_number():
    a = "FKM ist bis 400 °C dauerhaft einsetzbar."  # fabricated temperature, no source
    r = evaluate_render(
        answer_text=a, contract=C_GENERAL, check_sentence_coverage=False
    )
    assert not r.ok and r.action == "BLOCK"
    assert "invented_number" in {v.kind for v in r.violations}


def test_light_mode_still_blocks_invented_material():
    a = "FKM und NBR sind hier beide eine gute Wahl."  # NBR not in this turn's grounding
    r = evaluate_render(
        answer_text=a, contract=C_GENERAL, check_sentence_coverage=False
    )
    assert not r.ok and r.action == "BLOCK"
    assert "invented_material" in {v.kind for v in r.violations}


def test_light_mode_still_blocks_forbidden_phrase():
    a = "FKM ist hierfür freigegeben."
    r = evaluate_render(
        answer_text=a, contract=C_GENERAL, check_sentence_coverage=False
    )
    assert not r.ok and r.action == "BLOCK"
    assert "forbidden_phrase" in {v.kind for v in r.violations}


def test_light_mode_empty_required_clauses_never_blocks_on_missing_clause():
    # required_clauses is always () for a guard-only contract — the check is a structural no-op,
    # not just "usually satisfied"
    a = "FKM ist ein fluoriertes Elastomer."
    r = evaluate_render(
        answer_text=a, contract=C_GENERAL, check_sentence_coverage=False
    )
    assert "missing_required_clause" not in {v.kind for v in r.violations}
