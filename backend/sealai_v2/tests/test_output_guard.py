"""INC-NARRATOR-CONTRACT Phase 3 — claim-level output_guard truth table.

Validates the fail-closed enforcement over real contracts (built by build_contract) + crafted renders:
clean render passes; each defect (invented number/material, missing clause, forbidden phrase, foreign
technical sentence) fail-closes; user-stated values + linguistic transitions + clarification questions
pass. The guard is PURE/INERT — this tests the enforcement logic, not any prod behaviour.
"""

from sealai_v2.core.coverage import coverage_for
from sealai_v2.core.contracts import GroundingFact
from sealai_v2.core.output_guard import evaluate_render
from sealai_v2.core.response_contract import build_contract

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
