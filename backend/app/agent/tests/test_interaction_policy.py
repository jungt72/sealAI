"""
Table-driven tests for the Interaction Policy V1 (Phase 0A.2).

Verifies that:
- evaluate_policy() never calls an LLM (pure Python, deterministic)
- All four ResultForms can be reached
- Fast path vs structured path split is correct
- Missing-parameter signals are correctly surfaced
- Optional LLM intent hints adjust (but do not override) decisions
"""
from __future__ import annotations

import pytest

from app.agent.agent.interaction_policy import evaluate_policy
from app.agent.agent.policy import (
    InteractionPolicyDecision,
    ResultForm,
    RoutingPath,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_params(**kwargs) -> dict:
    """Build a minimal AgentState dict with the given operating conditions."""
    medium = kwargs.get("medium")
    pressure = kwargs.get("pressure")
    temperature = kwargs.get("temperature")
    material = kwargs.get("material")
    return {
        "sealing_state": {
            "asserted": {
                "medium_profile": {"name": medium} if medium else {},
                "machine_profile": {"material": material} if material else {},
                "operating_conditions": {
                    k: v for k, v in [("pressure", pressure), ("temperature", temperature)] if v
                },
            }
        }
    }


# ---------------------------------------------------------------------------
# Core routing table — result_form + path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected_form, expected_path", [
    # 1. Glossary / concept explanation → DIRECT_ANSWER / FAST
    ("Was ist FKM?", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),
    ("Was bedeutet NBR?", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),
    ("Was ist eine Labyrinthdichtung?", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),
    ("Erkläre mir den Begriff Shore-Härte.", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),
    ("Was versteht man unter AED?", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),

    # 2. Material comparison → DIRECT_ANSWER / FAST
    ("Vergleich FKM vs NBR für Hydrauliköl", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),
    ("Was ist der Unterschied zwischen PTFE und EPDM?", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),
    ("Welches Material ist besser als FKM für Heißdampf?", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),

    # 3. Open sealing guidance (no params) → GUIDED_RECOMMENDATION / FAST
    ("Welche Dichtung brauche ich für 200°C Hydrauliköl?", ResultForm.GUIDED_RECOMMENDATION, RoutingPath.FAST_PATH),
    ("Ich suche eine Dichtung für aggressives Medium.", ResultForm.GUIDED_RECOMMENDATION, RoutingPath.FAST_PATH),
    ("Welcher Werkstoff empfiehlt sich für Lebensmittelkontakt?", ResultForm.DIRECT_ANSWER, RoutingPath.FAST_PATH),

    # 4. Calculation with numeric evidence → DETERMINISTIC_RESULT / STRUCTURED
    ("Berechne RWDR für 50mm Welle, 3000 rpm", ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Umlaufgeschwindigkeit bei 80mm und 1450 U/min", ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Gleitgeschwindigkeit: Welle 60mm, 2000 rpm", ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),

    # 5. Certification / formal release → QUALIFIED_CASE / STRUCTURED
    ("Ich brauche eine FDA-konforme Freigabe für Anlage X", ResultForm.QUALIFIED_CASE, RoutingPath.STRUCTURED_PATH),
    ("Zertifikat für ATEX-Zone 1 benötigt", ResultForm.QUALIFIED_CASE, RoutingPath.STRUCTURED_PATH),
    ("Welche Materialien sind NORSOK-freigegeben?", ResultForm.QUALIFIED_CASE, RoutingPath.STRUCTURED_PATH),
    ("Herstellerfreigabe für Sonderkonstruktion", ResultForm.QUALIFIED_CASE, RoutingPath.STRUCTURED_PATH),
    ("RFQ für Druckbehälter-Dichtung nach DIN-Norm", ResultForm.QUALIFIED_CASE, RoutingPath.STRUCTURED_PATH),
])
def test_policy_result_form_and_path(query, expected_form, expected_path):
    decision = evaluate_policy(query)
    assert decision.result_form == expected_form, (
        f"Query: {query!r}\n"
        f"Expected form: {expected_form}, got: {decision.result_form}"
    )
    assert decision.path == expected_path, (
        f"Query: {query!r}\n"
        f"Expected path: {expected_path}, got: {decision.path}"
    )


# ---------------------------------------------------------------------------
# has_case_state consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected_has_case_state", [
    ("Was ist FKM?", False),
    ("Vergleich FKM vs NBR", False),
    ("Welche Dichtung für Heißdampf?", False),
    ("Berechne RWDR 50mm 1500 rpm", True),
    ("FDA Freigabe für Anlage", True),
])
def test_has_case_state(query, expected_has_case_state):
    decision = evaluate_policy(query)
    assert decision.has_case_state == expected_has_case_state, (
        f"Query: {query!r}: expected has_case_state={expected_has_case_state}, "
        f"got {decision.has_case_state}"
    )


# ---------------------------------------------------------------------------
# Missing-parameter surfacing
# ---------------------------------------------------------------------------

def test_guided_recommendation_surfaces_missing_params_when_no_state():
    """With no current_state, guidance must report missing critical params."""
    decision = evaluate_policy("Welche Dichtung für meine Pumpe?")
    assert decision.result_form == ResultForm.GUIDED_RECOMMENDATION
    assert "medium" in decision.required_fields
    assert "pressure" in decision.required_fields or "temperature" in decision.required_fields


def test_guided_recommendation_no_missing_params_when_state_complete():
    """With complete state, required_fields should be empty."""
    state = _state_with_params(medium="Hydrauliköl HLP46", pressure=200, temperature=80)
    decision = evaluate_policy("Welche Dichtung ist besser hier?", current_state=state)
    assert decision.result_form == ResultForm.GUIDED_RECOMMENDATION
    assert decision.required_fields == ()


def test_deterministic_result_notes_missing_params_when_calc_keyword_only():
    """'Berechne' with no numbers → DETERMINISTIC_RESULT but flags missing params."""
    decision = evaluate_policy("Berechne die Umlaufgeschwindigkeit")
    assert decision.result_form == ResultForm.DETERMINISTIC_RESULT
    assert len(decision.required_fields) > 0


# ---------------------------------------------------------------------------
# Optional LLM intent hint — adjusts but never overrides hard gates
# ---------------------------------------------------------------------------

def test_llm_intent_hint_glossary_boosts_direct_answer():
    """LLM hint 'glossary' on an ambiguous query pushes toward DIRECT_ANSWER."""
    # Without hint this could go guidance; with hint it should be direct answer
    decision = evaluate_policy("FKM", extracted_intent="glossary")
    assert decision.result_form == ResultForm.DIRECT_ANSWER


def test_llm_intent_hint_qualification_forces_qualified_case():
    """LLM hint 'qualification' on a neutral message must trigger QUALIFIED_CASE."""
    decision = evaluate_policy("Wir brauchen das für unsere Anlage", extracted_intent="qualification")
    assert decision.result_form == ResultForm.QUALIFIED_CASE
    assert decision.path == RoutingPath.STRUCTURED_PATH


def test_llm_intent_hint_cannot_downgrade_hard_qual_gate():
    """A 'Freigabe' keyword is a hard gate — even 'guidance' hint can't override it."""
    decision = evaluate_policy("Freigabe für FDA-Anwendung benötigt", extracted_intent="guidance")
    assert decision.result_form == ResultForm.QUALIFIED_CASE


# ---------------------------------------------------------------------------
# Return type is always InteractionPolicyDecision
# ---------------------------------------------------------------------------

def test_return_type():
    decision = evaluate_policy("anything")
    assert isinstance(decision, InteractionPolicyDecision)


def test_policy_version_is_set():
    decision = evaluate_policy("anything")
    assert decision.policy_version.startswith("interaction_policy_v")


# ---------------------------------------------------------------------------
# Default fallback: open-ended question does NOT go to heavy structured path
# This is the critical regression guard for the old keyword-only bug.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "Ich habe einen Hydraulikzylinder und suche eine Dichtung.",
    "Für meine Pumpenanlage welche Materialien?",
    "Dichtung für aggressive Medien gesucht.",
    "Bitte empfehlt mir etwas für hohe Temperaturen.",
])
def test_open_sealing_question_does_not_land_on_structured_path(query):
    """
    Regression guard: open sealing questions without qualification signals
    must NOT be routed to the heavy STRUCTURED_QUALIFICATION pipeline.
    """
    decision = evaluate_policy(query)
    assert decision.path == RoutingPath.FAST_PATH, (
        f"Open question routed to structured path (regression): {query!r}"
    )
    assert decision.result_form != ResultForm.QUALIFIED_CASE
