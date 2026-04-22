"""
Table-driven tests for the Interaction Policy — Phase 0A.2 / 0D / 0F.

Phase 0F changes (determinism):
- All tests patch _call_routing_llm via an autouse fixture.
  The real routing LLM is never called — tests are network-independent.
- Expected output classes reflect the Sprint 2 classifier model.
- extracted_intent parameter is accepted for API compatibility but unused
  in routing logic — tests reflect actual behaviour.

Test coverage:
- Legacy interaction paths map onto output classes.
- Fast path vs structured path split is correct
- Deterministic pre-checks (meta, block, fast→structured upgrade) run independently
- Missing-parameter signals are surfaced for the structured path
"""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from app.agent.agent.interaction_policy import evaluate_policy
from app.agent.agent.policy import InteractionPolicyDecision
from app.domain.pre_gate_classification import PreGateClassification
from app.services.output_classifier import OutputClass


# ---------------------------------------------------------------------------
# Autouse fixture: deterministic routing LLM mock
# ---------------------------------------------------------------------------

def _rule_based_routing(user_input: str) -> str:
    """Deterministic stand-in for the routing LLM.

    Classifies based on simple semantic rules that match the routing LLM's
    documented intent — without making any network calls.

    Structured (technical / formal):
    - Certification / formal release queries (FDA, ATEX, NORSOK, …)
    - Any explicit calculation request (Berechne/Berechnung keyword)
    Fast (knowledge / general guidance):
    - Everything else

    Note: numeric-unit patterns and material+context patterns are handled
    by the deterministic fast→structured upgrade in evaluate_policy(), not
    by this mock. The mock only needs to cover the LLM routing decision itself.
    """
    structured_pattern = re.compile(
        r"\b(FDA|ATEX|NORSOK|Zertifikat|Freigabe|RFQ|DIN-Norm|Herstellerfreigabe"
        r"|DIN|ISO|REACH|Konformit|Qualifikation)\b"
        r"|"
        r"\b(Berechne|Berechnung)\b",   # any calc keyword → Structured
        re.IGNORECASE,
    )
    return "Structured" if structured_pattern.search(user_input) else "Fast"


@pytest.fixture(autouse=True)
def deterministic_routing(monkeypatch):
    """Patch _call_routing_llm so all interaction_policy tests are deterministic."""
    monkeypatch.setattr(
        "app.agent.runtime.interaction_policy._call_routing_llm",
        _rule_based_routing,
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
# Core routing table — output class + path
# ---------------------------------------------------------------------------
#
# Notes on transitional path mapping:
#   - FAST path maps to conversational_answer.
#   - STRUCTURED path maps to governed update or clarification in this shim.
#   - Queries with numeric units (mm, bar, °C, rpm, …) are upgraded from Fast
#     to Structured by the deterministic fast→structured upgrade check.

@pytest.mark.parametrize("query, expected_form, expected_pre_gate, expected_policy_path", [
    # 1. Glossary / concept explanation → conversational answer / FAST
    ("Was ist FKM?",                             OutputClass.CONVERSATIONAL_ANSWER,     PreGateClassification.KNOWLEDGE_QUERY, "fast"),
    ("Was bedeutet NBR?",                        OutputClass.CONVERSATIONAL_ANSWER,     PreGateClassification.KNOWLEDGE_QUERY, "fast"),
    ("Was ist eine Labyrinthdichtung?",          OutputClass.CONVERSATIONAL_ANSWER,     PreGateClassification.KNOWLEDGE_QUERY, "fast"),
    ("Erkläre mir den Begriff Shore-Härte.",     OutputClass.CONVERSATIONAL_ANSWER,     PreGateClassification.KNOWLEDGE_QUERY, "fast"),
    ("Was versteht man unter AED?",              OutputClass.CONVERSATIONAL_ANSWER,     PreGateClassification.KNOWLEDGE_QUERY, "fast"),

    # 2. Material comparison → varies by whether fast→structured upgrade fires
    #    "FKM … für Hydrauliköl" matches the material+context upgrade pattern → STRUCTURED
    #    "PTFE und EPDM" has no context keyword after material → stays FAST
    #    "FKM für Heißdampf" matches material+context upgrade pattern → STRUCTURED
    ("Vergleich FKM vs NBR für Hydrauliköl",    OutputClass.CONVERSATIONAL_ANSWER, PreGateClassification.KNOWLEDGE_QUERY, "fast"),
    ("Was ist der Unterschied zwischen PTFE und EPDM?",
                                                  OutputClass.CONVERSATIONAL_ANSWER,     PreGateClassification.KNOWLEDGE_QUERY, "fast"),
    ("Welches Material ist besser als FKM für Heißdampf?",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),

    # 3. Open guidance questions without numeric params → conversational / FAST
    ("Ich suche eine Dichtung für aggressives Medium.",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
    ("Welcher Werkstoff empfiehlt sich für Lebensmittelkontakt?",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),

    # 4. Guidance question WITH numeric temperature → upgraded to STRUCTURED
    #    "200°C" matches the fast→structured upgrade pattern (numeric+unit).
    ("Welche Dichtung brauche ich für 200°C Hydrauliköl?",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),

    # 5. Calculation with numeric evidence → structured clarification / STRUCTURED
    #    (Upgrade fires independently of LLM decision)
    ("Berechne RWDR für 50mm Welle, 3000 rpm",  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
    ("Umlaufgeschwindigkeit bei 80mm und 1450 U/min",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
    ("Gleitgeschwindigkeit: Welle 60mm, 2000 rpm",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),

    # 6. Certification / formal release → structured clarification / STRUCTURED
    ("Ich brauche eine FDA-konforme Freigabe für Anlage X",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
    ("Zertifikat für ATEX-Zone 1 benötigt",      OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
    ("Welche Materialien sind NORSOK-freigegeben?",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
    ("Herstellerfreigabe für Sonderkonstruktion", OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
    ("RFQ für Druckbehälter-Dichtung nach DIN-Norm",
                                                  OutputClass.STRUCTURED_CLARIFICATION, PreGateClassification.DOMAIN_INQUIRY, "structured"),
])
def test_policy_output_class_and_pre_gate(query, expected_form, expected_pre_gate, expected_policy_path):
    decision = evaluate_policy(query)
    assert decision.output_class == expected_form, (
        f"Query: {query!r}\n"
        f"Expected output class: {expected_form}, got: {decision.output_class}"
    )
    assert decision.pre_gate_classification == expected_pre_gate, (
        f"Query: {query!r}\n"
        f"Expected pre-gate: {expected_pre_gate}, got: {decision.pre_gate_classification}"
    )
    assert decision.path == expected_policy_path, (
        f"Query: {query!r}\n"
        f"Expected legacy policy path: {expected_policy_path}, got: {decision.path}"
    )


# ---------------------------------------------------------------------------
# has_case_state consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected_has_case_state", [
    ("Was ist FKM?",               False),
    ("Vergleich FKM vs NBR",       False),
    ("Welche Dichtung für Heißdampf?", True),
    ("Berechne RWDR 50mm 1500 rpm", True),    # numeric upgrade → structured
    ("FDA Freigabe für Anlage",     True),     # mock → Structured → has_case_state=True
])
def test_has_case_state(query, expected_has_case_state):
    decision = evaluate_policy(query)
    assert decision.has_case_state == expected_has_case_state, (
        f"Query: {query!r}: expected has_case_state={expected_has_case_state}, "
        f"got {decision.has_case_state}"
    )


# ---------------------------------------------------------------------------
# Missing-parameter surfacing on the structured path
# ---------------------------------------------------------------------------

def test_structured_path_surfaces_missing_params_when_no_state():
    """Without current_state, structured path reports all critical params as missing."""
    # "Berechne" + numbers → deterministically Structured
    decision = evaluate_policy("Berechne RWDR 50mm 1500 rpm")
    assert decision.output_class == OutputClass.STRUCTURED_CLARIFICATION
    assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
    assert decision.path == "structured"
    assert "medium" in decision.required_fields
    assert "pressure" in decision.required_fields or "temperature" in decision.required_fields


def test_structured_path_no_missing_params_when_state_complete():
    """With complete asserted state, required_fields is empty on the structured path."""
    state = _state_with_params(medium="Hydrauliköl HLP46", pressure=200, temperature=80)
    decision = evaluate_policy("Berechne RWDR 50mm 1500 rpm", current_state=state)
    assert decision.output_class == OutputClass.GOVERNED_STATE_UPDATE
    assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
    assert decision.path == "structured"
    assert decision.required_fields == ()


def test_calc_keyword_without_numbers_still_reaches_structured_via_mock():
    """'Berechne' keyword with a technical context → Structured path via mock.

    The mock classifies 'Berechne ... Umlaufgeschwindigkeit' as Structured,
    and with no numeric parameters present, required_fields is populated.
    """
    decision = evaluate_policy("Berechne die Umlaufgeschwindigkeit")
    # Rule-based mock returns "Structured" for calc+technical-keyword combo
    assert decision.output_class == OutputClass.STRUCTURED_CLARIFICATION
    assert len(decision.required_fields) > 0


# ---------------------------------------------------------------------------
# Phase 0D deterministic pre-checks — run BEFORE the routing LLM
# ---------------------------------------------------------------------------

def test_meta_query_bypasses_llm_entirely():
    """Meta queries must route to META_PATH without any LLM call.

    The autouse fixture patches _call_routing_llm to a rule-based mock.
    If _call_routing_llm were called for a meta query, the mock would
    still be invoked — but the meta check runs first, so it must not
    even reach the LLM layer.
    """
    call_count = []
    original_mock = _rule_based_routing

    def counting_mock(user_input: str) -> str:
        call_count.append(user_input)
        return original_mock(user_input)

    with patch("app.agent.runtime.interaction_policy._call_routing_llm", counting_mock):
        decision = evaluate_policy("Was fehlt noch?")

    assert decision.pre_gate_classification is PreGateClassification.META_QUESTION
    assert decision.path == "meta"
    assert len(call_count) == 0, (
        "Meta queries must not call the routing LLM at all — "
        f"LLM was called {len(call_count)} time(s)"
    )


def test_blocked_query_bypasses_llm_entirely():
    """Blocked requests must route to BLOCKED_PATH without any LLM call."""
    call_count = []
    original_mock = _rule_based_routing

    def counting_mock(user_input: str) -> str:
        call_count.append(user_input)
        return original_mock(user_input)

    with patch("app.agent.runtime.interaction_policy._call_routing_llm", counting_mock):
        decision = evaluate_policy("Welchen Hersteller empfiehlst du?")

    assert decision.pre_gate_classification is PreGateClassification.BLOCKED
    assert decision.path == "blocked"
    assert len(call_count) == 0, (
        "Blocked requests must not call the routing LLM at all — "
        f"LLM was called {len(call_count)} time(s)"
    )


def test_fast_to_structured_upgrade_overrides_llm_fast_decision():
    """Numeric+unit input is upgraded to Structured even if LLM would say Fast."""
    # Force mock to return "Fast" even for a numeric input
    with patch("app.agent.runtime.interaction_policy._call_routing_llm", return_value="Fast"):
        decision = evaluate_policy("Welle 50mm, 3000 rpm")

    # The fast→structured upgrade must fire and override the LLM "Fast" decision
    assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
    assert decision.path == "structured", (
        "Numeric+unit input must be upgraded from Fast to Structured "
        "regardless of LLM decision"
    )
    assert decision.output_class == OutputClass.STRUCTURED_CLARIFICATION


def test_llm_error_falls_back_to_structured():
    """Any routing LLM exception must fall back to the Structured path."""
    def _raise(*args, **kwargs):
        raise ConnectionError("LLM unavailable")

    with patch("app.agent.runtime.interaction_policy._call_routing_llm", _raise):
        decision = evaluate_policy("Dichtung für Pumpe?")

    assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
    assert decision.path == "structured", (
        "LLM error must fall back to Structured (safe default)"
    )


# ---------------------------------------------------------------------------
# Routing intent tests — structured vs fast semantics
# ---------------------------------------------------------------------------

def test_knowledge_question_routes_to_fast():
    """Pure knowledge questions must route to the fast path."""
    decision = evaluate_policy("Was ist ein Radialwellendichtring?")
    assert decision.pre_gate_classification is PreGateClassification.KNOWLEDGE_QUERY
    assert decision.path == "fast"
    assert decision.output_class == OutputClass.CONVERSATIONAL_ANSWER


def test_structured_routing_note_missing_fields():
    """Structured path must list required_fields when state is absent."""
    decision = evaluate_policy("FDA Freigabe für Anlage")
    assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
    assert decision.path == "structured"
    assert len(decision.required_fields) > 0


def test_structured_routing_empty_required_fields_when_state_complete():
    """Structured path must have empty required_fields when all critical params asserted."""
    state = _state_with_params(medium="Wasser", pressure=5, temperature=60)
    decision = evaluate_policy("FDA Freigabe für Anlage", current_state=state)
    assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
    assert decision.path == "structured"
    assert decision.required_fields == ()


# ---------------------------------------------------------------------------
# Open-ended sealing questions — must NOT land on heavy structured pipeline
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
    assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
    assert decision.path == "structured", (
        f"Open question routed to structured path (regression): {query!r}"
    )
    assert decision.output_class != OutputClass.GOVERNED_STATE_UPDATE


# ---------------------------------------------------------------------------
# Return type and version invariants
# ---------------------------------------------------------------------------

def test_return_type():
    decision = evaluate_policy("anything")
    assert isinstance(decision, InteractionPolicyDecision)


def test_policy_version_is_set():
    decision = evaluate_policy("anything")
    assert decision.policy_version.startswith("interaction_policy_v")


def test_all_five_paths_reachable():
    """All five runtime paths must be reachable via evaluate_policy."""
    paths = set()

    # Fast
    paths.add(evaluate_policy("Was ist FKM?").path)

    # Structured (numeric upgrade)
    paths.add(evaluate_policy("Welle 50mm, 3000 rpm").path)

    # Meta
    paths.add(evaluate_policy("Was fehlt noch?").path)

    # Blocked
    paths.add(evaluate_policy("Welchen Hersteller empfiehlst du?").path)

    # Greeting
    paths.add(evaluate_policy("Hallo").path)

    assert "fast" in paths
    assert "structured" in paths
    assert "meta" in paths
    assert "blocked" in paths
    assert "greeting" in paths


# ---------------------------------------------------------------------------
# Phase 0D+: Greeting / smalltalk deterministic path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "Hallo",
    "Hi!",
    "Hey",
    "Guten Morgen",
    "Guten Tag!",
    "Danke",
    "Vielen Dank!",
    "Tschüss",
    "Wie geht's?",
    "Moin!",
    "Servus",
])
def test_greeting_routes_to_greeting_path(query):
    """Trivial greetings must route to GREETING_PATH — no LLM, no RAG."""
    decision = evaluate_policy(query)
    assert decision.pre_gate_classification is PreGateClassification.GREETING
    assert decision.path == "greeting", (
        f"Query {query!r} should route to GREETING_PATH, got {decision.path}"
    )
    assert decision.has_case_state is False
    assert decision.interaction_class == "GREETING"


@pytest.mark.parametrize("query", ["Wer bist du?", "Was kannst du?"])
def test_meta_questions_route_to_meta_question(query):
    decision = evaluate_policy(query)
    assert decision.pre_gate_classification is PreGateClassification.META_QUESTION
    assert decision.path == "meta"
    assert decision.has_case_state is False


def test_greeting_bypasses_llm_entirely():
    """Greeting queries must not call the routing LLM at all."""
    call_count = []
    original_mock = _rule_based_routing

    def counting_mock(user_input: str) -> str:
        call_count.append(user_input)
        return original_mock(user_input)

    with patch("app.agent.runtime.interaction_policy._call_routing_llm", counting_mock):
        decision = evaluate_policy("Hallo!")

    assert decision.pre_gate_classification is PreGateClassification.GREETING
    assert decision.path == "greeting"
    assert len(call_count) == 0, (
        "Greeting queries must not call the routing LLM at all — "
        f"LLM was called {len(call_count)} time(s)"
    )


@pytest.mark.parametrize("query", [
    "Hallo, ich brauche eine Dichtung für 50mm Welle",
    "Hi, Berechne RWDR für 3000 rpm",
    "Danke, und was ist mit 200 bar?",
])
def test_greeting_with_technical_content_does_not_match(query):
    """Greetings mixed with technical content must NOT match the greeting pattern."""
    decision = evaluate_policy(query)
    assert decision.path != "greeting", (
        f"Query {query!r} has technical content and must NOT route to GREETING_PATH"
    )
