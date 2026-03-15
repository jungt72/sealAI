"""
0A.2: Interaction Policy V1 — table-driven test matrix.

Tests cover:
- direct (knowledge / explanation intent) → fast path
- deterministic (calc with numeric inputs) → fast path
- guided (guidance keywords, or qual signal without data basis) → structured path
- qualified (qual signal with asserted state basis, or RWDR payload) → structured path
- boundary_flags and coverage_status correctness
- escalation_reason on qualification downgrade
- backward-compatible route_interaction() wrapper
"""
import pytest

from app.agent.runtime import (
    InteractionPolicyDecision,
    evaluate_interaction_policy,
    route_interaction,
    _has_asserted_parameters,
    _is_knowledge_intent,
    _derive_required_fields,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal AgentState with asserted parameters
# ---------------------------------------------------------------------------

def _state_with_asserted_medium(medium: str = "Wasser") -> dict:
    return {
        "sealing_state": {
            "asserted": {
                "medium_profile": {"name": medium},
                "operating_conditions": {},
            },
            "governance": {
                "unknowns_release_blocking": [],
            },
        }
    }


def _state_with_asserted_conditions(temperature: float = 150.0, pressure: float = 10.0) -> dict:
    return {
        "sealing_state": {
            "asserted": {
                "medium_profile": {},
                "operating_conditions": {"temperature": temperature, "pressure": pressure},
            },
            "governance": {
                "unknowns_release_blocking": ["medium_identity_unresolved"],
            },
        }
    }


def _state_with_no_params() -> dict:
    return {
        "sealing_state": {
            "asserted": {
                "medium_profile": {},
                "operating_conditions": {},
            },
            "governance": {
                "unknowns_release_blocking": [],
            },
        }
    }


# ---------------------------------------------------------------------------
# Table-driven policy matrix
# ---------------------------------------------------------------------------

_POLICY_CASES = [
    # --- Knowledge / direct / fast ---
    pytest.param(
        "Was ist PTFE?", False, None, "direct", "fast",
        id="knowledge_was_ist",
    ),
    pytest.param(
        "Erkläre mir FKM", False, None, "direct", "fast",
        id="knowledge_erklaere",
    ),
    pytest.param(
        "Unterschied zwischen NBR und EPDM", False, None, "direct", "fast",
        id="knowledge_unterschied",
    ),
    pytest.param(
        "Wie funktioniert ein Wellendichtring?", False, None, "direct", "fast",
        id="knowledge_wie_funktioniert",
    ),
    pytest.param(
        "What is a shaft seal?", False, None, "direct", "fast",
        id="knowledge_what_is_en",
    ),
    pytest.param(
        "Wie funktioniert eine RWDR?", False, None, "direct", "fast",
        id="knowledge_prefix_beats_qualification_keyword",
    ),
    pytest.param(
        "Erkläre den Unterschied zwischen PTFE und FKM bei Hochtemperatur", False, None, "direct", "fast",
        id="knowledge_erklaere_comparison",
    ),
    pytest.param(
        "Warum versagt NBR bei hohen Temperaturen?", False, None, "direct", "fast",
        id="knowledge_warum",
    ),

    # --- Deterministic / fast calc ---
    pytest.param(
        "Berechne v: 50mm, 3000 rpm", False, None, "deterministic", "fast",
        id="calc_berechne_v",
    ),
    pytest.param(
        "calculate surface speed: diameter 40mm, speed 1500 rpm", False, None, "deterministic", "fast",
        id="calc_calculate_en",
    ),
    pytest.param(
        "PV bei 40mm, 1500 rpm, 5 bar", False, None, "deterministic", "fast",
        id="calc_pv_with_inputs",
    ),
    pytest.param(
        "Umfangsgeschwindigkeit berechnen: Durchmesser 60mm, Drehzahl 2000 rpm", False, None, "deterministic", "fast",
        id="calc_umfangsgeschwindigkeit",
    ),

    # --- Guided / structured ---
    pytest.param(
        "Dichtung für Wasser bei 150°C", False, None, "guided", "structured",
        id="guided_seal_water_temp",
    ),
    pytest.param(
        "Ich brauche eine Dichtung für meine Anwendung", False, None, "guided", "structured",
        id="guided_two_keywords",
    ),
    pytest.param(
        "Wellenabdichtung bei 10 bar Druck", False, None, "guided", "structured",
        id="guided_shaft_seal_pressure",
    ),
    pytest.param(
        "Medium: Öl, Temperatur: 200°C, Druck: 20 bar", False, None, "guided", "structured",
        id="guided_full_params_no_qual_keyword",
    ),
    pytest.param(
        "Was ist die beste Dichtung für 200°C?", False, None, "guided", "structured",
        id="guided_question_with_guidance_keywords_and_temp",
    ),

    # --- Guided (qualification downgrade — no data basis) ---
    pytest.param(
        "Empfehle ein Material", False, None, "guided", "structured",
        id="qual_downgrade_no_state",
    ),
    pytest.param(
        "Materialauswahl treffen", False, None, "guided", "structured",
        id="qual_downgrade_materialauswahl",
    ),
    pytest.param(
        "Welches Material ist geeignet?", False, None, "guided", "structured",
        id="qual_downgrade_geeignet",
    ),

    # --- Qualified — with asserted state basis ---
    pytest.param(
        "Empfehle ein Material", False, _state_with_asserted_medium(), "qualified", "structured",
        id="qualified_with_medium_basis",
    ),
    pytest.param(
        "Material freigeben", False, _state_with_asserted_conditions(), "qualified", "structured",
        id="qualified_with_conditions_basis",
    ),

    # --- Qualified — RWDR payload ---
    pytest.param(
        "Hallo", True, None, "qualified", "structured",
        id="rwdr_payload_any_message",
    ),
    pytest.param(
        "Beliebige Nachricht", True, None, "qualified", "structured",
        id="rwdr_payload_arbitrary",
    ),

    # --- Fallback / safe structured ---
    pytest.param(
        "Hallo", False, None, "guided", "structured",
        id="fallback_greeting",
    ),
    pytest.param(
        "Ich brauche Hilfe", False, None, "guided", "structured",
        id="fallback_help_request",
    ),
    pytest.param(
        "", False, None, "guided", "structured",
        id="fallback_empty_message",
    ),
]


@pytest.mark.parametrize("message,has_rwdr,state,expected_form,expected_path", _POLICY_CASES)
def test_policy_result_form_and_path(message, has_rwdr, state, expected_form, expected_path):
    decision = evaluate_interaction_policy(
        message,
        has_rwdr_payload=has_rwdr,
        existing_state=state,
    )
    assert isinstance(decision, InteractionPolicyDecision)
    assert decision.result_form == expected_form, (
        f"result_form mismatch for {message!r}: got {decision.result_form!r}, expected {expected_form!r}"
    )
    assert decision.path == expected_path, (
        f"path mismatch for {message!r}: got {decision.path!r}, expected {expected_path!r}"
    )


# ---------------------------------------------------------------------------
# stream_mode tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message,has_rwdr,state,expected_stream_mode", [
    ("Was ist PTFE?", False, None, "direct_answer_stream"),
    ("Berechne v: 50mm, 3000 rpm", False, None, "direct_answer_stream"),
    ("Dichtung für Wasser bei 150°C", False, None, "structured_progress_stream"),
    ("Empfehle ein Material", False, None, "structured_progress_stream"),
    ("Empfehle ein Material", False, _state_with_asserted_medium(), "structured_progress_stream"),
    ("Test", True, None, "structured_progress_stream"),
])
def test_policy_stream_mode(message, has_rwdr, state, expected_stream_mode):
    decision = evaluate_interaction_policy(message, has_rwdr_payload=has_rwdr, existing_state=state)
    assert decision.stream_mode == expected_stream_mode


# ---------------------------------------------------------------------------
# boundary_flags tests
# ---------------------------------------------------------------------------

def test_fast_path_has_boundary_flags():
    decision = evaluate_interaction_policy("Was ist PTFE?", has_rwdr_payload=False)
    assert "orientation_only" in decision.boundary_flags
    assert "no_manufacturer_release" in decision.boundary_flags


def test_calc_path_has_boundary_flags():
    decision = evaluate_interaction_policy("Berechne v: 50mm, 3000 rpm", has_rwdr_payload=False)
    assert "orientation_only" in decision.boundary_flags
    assert "no_manufacturer_release" in decision.boundary_flags


def test_guided_path_has_boundary_flags():
    decision = evaluate_interaction_policy("Dichtung für Wasser bei 150°C", has_rwdr_payload=False)
    assert "orientation_only" in decision.boundary_flags
    assert "no_manufacturer_release" in decision.boundary_flags


def test_qualified_path_no_orientation_only_flag():
    decision = evaluate_interaction_policy(
        "Empfehle ein Material",
        has_rwdr_payload=False,
        existing_state=_state_with_asserted_medium(),
    )
    assert decision.result_form == "qualified"
    assert "orientation_only" not in decision.boundary_flags


def test_rwdr_payload_no_boundary_flags():
    decision = evaluate_interaction_policy("Test", has_rwdr_payload=True)
    assert decision.result_form == "qualified"
    assert decision.boundary_flags == ()


# ---------------------------------------------------------------------------
# coverage_status tests
# ---------------------------------------------------------------------------

def test_rwdr_payload_in_scope():
    decision = evaluate_interaction_policy("Test", has_rwdr_payload=True)
    assert decision.coverage_status == "in_scope"


def test_calc_in_scope():
    decision = evaluate_interaction_policy("Berechne v: 50mm, 3000 rpm", has_rwdr_payload=False)
    assert decision.coverage_status == "in_scope"


def test_knowledge_unknown_coverage():
    decision = evaluate_interaction_policy("Was ist PTFE?", has_rwdr_payload=False)
    assert decision.coverage_status == "unknown"


def test_guided_partial_coverage():
    decision = evaluate_interaction_policy("Dichtung für Wasser bei 150°C", has_rwdr_payload=False)
    assert decision.coverage_status == "partial"


def test_qualified_downgrade_partial_coverage():
    decision = evaluate_interaction_policy("Empfehle ein Material", has_rwdr_payload=False)
    assert decision.coverage_status == "partial"


def test_fallback_unknown_coverage():
    decision = evaluate_interaction_policy("Hallo", has_rwdr_payload=False)
    assert decision.coverage_status == "unknown"


# ---------------------------------------------------------------------------
# escalation_reason tests
# ---------------------------------------------------------------------------

def test_qualification_downgrade_sets_escalation_reason():
    decision = evaluate_interaction_policy("Empfehle ein Material", has_rwdr_payload=False)
    assert decision.result_form == "guided"
    assert decision.escalation_reason == "qualification_signal_without_data_basis"


def test_no_escalation_reason_for_direct():
    decision = evaluate_interaction_policy("Was ist PTFE?", has_rwdr_payload=False)
    assert decision.escalation_reason is None


def test_no_escalation_reason_for_guided_genuine():
    decision = evaluate_interaction_policy("Dichtung für Wasser bei 150°C", has_rwdr_payload=False)
    assert decision.escalation_reason is None


def test_no_escalation_reason_for_qualified():
    decision = evaluate_interaction_policy(
        "Empfehle ein Material",
        has_rwdr_payload=False,
        existing_state=_state_with_asserted_medium(),
    )
    assert decision.escalation_reason is None


def test_no_escalation_reason_for_rwdr():
    decision = evaluate_interaction_policy("Test", has_rwdr_payload=True)
    assert decision.escalation_reason is None


# ---------------------------------------------------------------------------
# required_fields from existing state governance
# ---------------------------------------------------------------------------

def test_required_fields_surfaced_from_governance():
    state = {
        "sealing_state": {
            "asserted": {
                "medium_profile": {"name": "Wasser"},
                "operating_conditions": {"temperature": 150.0},
            },
            "governance": {
                "unknowns_release_blocking": ["manufacturer_name_unresolved", "grade_name_unresolved"],
            },
        }
    }
    decision = evaluate_interaction_policy(
        "Empfehle ein Material",
        has_rwdr_payload=False,
        existing_state=state,
    )
    assert "manufacturer_name_unresolved" in decision.required_fields
    assert "grade_name_unresolved" in decision.required_fields


def test_required_fields_empty_without_state():
    decision = evaluate_interaction_policy("Dichtung für Wasser bei 150°C", has_rwdr_payload=False)
    assert decision.required_fields == ()


# ---------------------------------------------------------------------------
# backward compatibility: route_interaction() wrapper
# ---------------------------------------------------------------------------

def test_route_interaction_returns_runtime_decision():
    from app.agent.runtime import RuntimeDecision
    result = route_interaction("Was ist PTFE?")
    assert isinstance(result, RuntimeDecision)
    assert result.interaction_class == "KNOWLEDGE"
    assert result.runtime_path == "FAST_KNOWLEDGE"
    assert result.binding_level == "KNOWLEDGE"
    assert result.has_case_state is False


def test_route_interaction_calc():
    result = route_interaction("Berechne v: 50mm, 3000 rpm")
    assert result.runtime_path == "FAST_CALCULATION"
    assert result.has_case_state is False


def test_route_interaction_guidance():
    result = route_interaction("Dichtung für Wasser bei 150°C")
    assert result.interaction_class == "GUIDANCE"
    assert result.has_case_state is True


def test_route_interaction_rwdr_payload():
    result = route_interaction("Hallo", has_rwdr_payload=True)
    assert result.interaction_class == "QUALIFICATION"
    assert result.runtime_path == "STRUCTURED_QUALIFICATION"
    assert result.has_case_state is True


def test_route_interaction_fallback():
    result = route_interaction("Hallo")
    assert result.has_case_state is True


# ---------------------------------------------------------------------------
# Gate helper unit tests
# ---------------------------------------------------------------------------

def test_has_asserted_parameters_none_state():
    assert _has_asserted_parameters(None) is False


def test_has_asserted_parameters_empty_state():
    assert _has_asserted_parameters(_state_with_no_params()) is False


def test_has_asserted_parameters_with_medium():
    assert _has_asserted_parameters(_state_with_asserted_medium()) is True


def test_has_asserted_parameters_with_temperature():
    assert _has_asserted_parameters(_state_with_asserted_conditions()) is True


def test_is_knowledge_intent_warum():
    assert _is_knowledge_intent("warum versagt nbr bei hitze?") is True


def test_is_knowledge_intent_guidance_override():
    assert _is_knowledge_intent("was ist die beste dichtung für 200°c?") is False


def test_is_knowledge_intent_empty():
    assert _is_knowledge_intent("") is False


def test_derive_required_fields_empty():
    assert _derive_required_fields(None) == ()


def test_derive_required_fields_from_governance():
    state = {
        "sealing_state": {
            "governance": {
                "unknowns_release_blocking": ["a", "b", "c", "d"],
            }
        }
    }
    result = _derive_required_fields(state)
    assert result == ("a", "b", "c")  # capped at 3


# ---------------------------------------------------------------------------
# interaction_class backward compatibility on InteractionPolicyDecision
# ---------------------------------------------------------------------------

def test_policy_decision_has_interaction_class_knowledge():
    d = evaluate_interaction_policy("Was ist PTFE?")
    assert d.interaction_class == "KNOWLEDGE"


def test_policy_decision_has_interaction_class_calculation():
    d = evaluate_interaction_policy("Berechne v: 50mm, 3000 rpm")
    assert d.interaction_class == "CALCULATION"


def test_policy_decision_has_interaction_class_guidance():
    d = evaluate_interaction_policy("Dichtung für Wasser bei 150°C")
    assert d.interaction_class == "GUIDANCE"


def test_policy_decision_has_interaction_class_qualification():
    d = evaluate_interaction_policy("Test", has_rwdr_payload=True)
    assert d.interaction_class == "QUALIFICATION"
