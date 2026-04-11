"""
Table-driven tests for the Interaction Policy — Phase 0A.2 / 0D / 0F.

Phase 0F changes (determinism):
- All tests patch _call_routing_llm via an autouse fixture.
  The real routing LLM is never called — tests are network-independent.
- Expected result forms updated to reflect Phase 0D behaviour:
    GUIDED_RECOMMENDATION → DIRECT_ANSWER  (fast path: knowledge/guidance combined)
    QUALIFIED_CASE        → DETERMINISTIC_RESULT  (unified structured result form)
- extracted_intent parameter is accepted for API compatibility but unused
  in routing logic — tests reflect actual behaviour.

Test coverage:
- All four result forms reachable (DIRECT_ANSWER, DETERMINISTIC_RESULT, META, BLOCKED)
- Fast path vs structured path split is correct
- Deterministic pre-checks (meta, block, fast→structured upgrade) run independently
- Missing-parameter signals are surfaced for the structured path
"""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from app.agent.agent.interaction_policy import evaluate_policy
from app.agent.agent.policy import (
    InteractionPolicyDecision,
    ResultForm,
    RoutingPath,
)


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
# Core routing table — result_form + path
# ---------------------------------------------------------------------------
#
# Notes on Phase 0D form changes:
#   - FAST path always returns DIRECT_ANSWER  (GUIDED_RECOMMENDATION removed)
#   - STRUCTURED path always returns DETERMINISTIC_RESULT  (QUALIFIED_CASE removed)
#   - Queries with numeric units (mm, bar, °C, rpm, …) are upgraded from Fast
#     to Structured by the deterministic fast→structured upgrade check.

@pytest.mark.parametrize("query, expected_form, expected_path", [
    # 1. Glossary / concept explanation → DIRECT_ANSWER / FAST
    ("Was ist FKM?",                             ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),
    ("Was bedeutet NBR?",                        ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),
    ("Was ist eine Labyrinthdichtung?",          ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),
    ("Erkläre mir den Begriff Shore-Härte.",     ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),
    ("Was versteht man unter AED?",              ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),

    # 2. Material comparison → varies by whether fast→structured upgrade fires
    #    "FKM … für Hydrauliköl" matches the material+context upgrade pattern → STRUCTURED
    #    "PTFE und EPDM" has no context keyword after material → stays FAST
    #    "FKM für Heißdampf" matches material+context upgrade pattern → STRUCTURED
    ("Vergleich FKM vs NBR für Hydrauliköl",    ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Was ist der Unterschied zwischen PTFE und EPDM?",
                                                  ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),
    ("Welches Material ist besser als FKM für Heißdampf?",
                                                  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),

    # 3. Open guidance questions without numeric params → DIRECT_ANSWER / FAST
    #    (Phase 0D: GUIDED_RECOMMENDATION form removed from fast path)
    ("Ich suche eine Dichtung für aggressives Medium.",
                                                  ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),
    ("Welcher Werkstoff empfiehlt sich für Lebensmittelkontakt?",
                                                  ResultForm.DIRECT_ANSWER,     RoutingPath.FAST_PATH),

    # 4. Guidance question WITH numeric temperature → upgraded to STRUCTURED
    #    "200°C" matches the fast→structured upgrade pattern (numeric+unit).
    ("Welche Dichtung brauche ich für 200°C Hydrauliköl?",
                                                  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),

    # 5. Calculation with numeric evidence → DETERMINISTIC_RESULT / STRUCTURED
    #    (Upgrade fires independently of LLM decision)
    ("Berechne RWDR für 50mm Welle, 3000 rpm",  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Umlaufgeschwindigkeit bei 80mm und 1450 U/min",
                                                  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Gleitgeschwindigkeit: Welle 60mm, 2000 rpm",
                                                  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),

    # 6. Certification / formal release → DETERMINISTIC_RESULT / STRUCTURED
    #    (Phase 0D: QUALIFIED_CASE form replaced by DETERMINISTIC_RESULT)
    ("Ich brauche eine FDA-konforme Freigabe für Anlage X",
                                                  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Zertifikat für ATEX-Zone 1 benötigt",      ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Welche Materialien sind NORSOK-freigegeben?",
                                                  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("Herstellerfreigabe für Sonderkonstruktion", ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
    ("RFQ für Druckbehälter-Dichtung nach DIN-Norm",
                                                  ResultForm.DETERMINISTIC_RESULT, RoutingPath.STRUCTURED_PATH),
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
    ("Was ist FKM?",               False),
    ("Vergleich FKM vs NBR",       False),
    ("Welche Dichtung für Heißdampf?", False),
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
    assert decision.result_form == ResultForm.DETERMINISTIC_RESULT
    assert decision.path == RoutingPath.STRUCTURED_PATH
    assert "medium" in decision.required_fields
    assert "pressure" in decision.required_fields or "temperature" in decision.required_fields


def test_structured_path_no_missing_params_when_state_complete():
    """With complete asserted state, required_fields is empty on the structured path."""
    state = _state_with_params(medium="Hydrauliköl HLP46", pressure=200, temperature=80)
    decision = evaluate_policy("Berechne RWDR 50mm 1500 rpm", current_state=state)
    assert decision.result_form == ResultForm.DETERMINISTIC_RESULT
    assert decision.path == RoutingPath.STRUCTURED_PATH
    assert decision.required_fields == ()


def test_calc_keyword_without_numbers_still_reaches_structured_via_mock():
    """'Berechne' keyword with a technical context → Structured path via mock.

    The mock classifies 'Berechne ... Umlaufgeschwindigkeit' as Structured,
    and with no numeric parameters present, required_fields is populated.
    """
    decision = evaluate_policy("Berechne die Umlaufgeschwindigkeit")
    # Rule-based mock returns "Structured" for calc+technical-keyword combo
    assert decision.result_form == ResultForm.DETERMINISTIC_RESULT
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

    assert decision.path == RoutingPath.META_PATH
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

    assert decision.path == RoutingPath.BLOCKED_PATH
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
    assert decision.path == RoutingPath.STRUCTURED_PATH, (
        "Numeric+unit input must be upgraded from Fast to Structured "
        "regardless of LLM decision"
    )
    assert decision.result_form == ResultForm.DETERMINISTIC_RESULT


def test_llm_error_falls_back_to_structured():
    """Any routing LLM exception must fall back to the Structured path."""
    def _raise(*args, **kwargs):
        raise ConnectionError("LLM unavailable")

    with patch("app.agent.runtime.interaction_policy._call_routing_llm", _raise):
        decision = evaluate_policy("Dichtung für Pumpe?")

    assert decision.path == RoutingPath.STRUCTURED_PATH, (
        "LLM error must fall back to Structured (safe default)"
    )


# ---------------------------------------------------------------------------
# Routing intent tests — structured vs fast semantics
# ---------------------------------------------------------------------------

def test_knowledge_question_routes_to_fast():
    """Pure knowledge questions must route to the fast path."""
    decision = evaluate_policy("Was ist ein Radialwellendichtring?")
    assert decision.path == RoutingPath.FAST_PATH
    assert decision.result_form == ResultForm.DIRECT_ANSWER


def test_structured_routing_note_missing_fields():
    """Structured path must list required_fields when state is absent."""
    decision = evaluate_policy("FDA Freigabe für Anlage")
    assert decision.path == RoutingPath.STRUCTURED_PATH
    assert len(decision.required_fields) > 0


def test_structured_routing_empty_required_fields_when_state_complete():
    """Structured path must have empty required_fields when all critical params asserted."""
    state = _state_with_params(medium="Wasser", pressure=5, temperature=60)
    decision = evaluate_policy("FDA Freigabe für Anlage", current_state=state)
    assert decision.path == RoutingPath.STRUCTURED_PATH
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
    assert decision.path == RoutingPath.FAST_PATH, (
        f"Open question routed to structured path (regression): {query!r}"
    )
    assert decision.result_form != ResultForm.DETERMINISTIC_RESULT


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

    assert RoutingPath.FAST_PATH in paths
    assert RoutingPath.STRUCTURED_PATH in paths
    assert RoutingPath.META_PATH in paths
    assert RoutingPath.BLOCKED_PATH in paths
    assert RoutingPath.GREETING_PATH in paths


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
    "Wer bist du?",
    "Was kannst du?",
    "Moin!",
    "Servus",
])
def test_greeting_routes_to_greeting_path(query):
    """Trivial greetings must route to GREETING_PATH — no LLM, no RAG."""
    decision = evaluate_policy(query)
    assert decision.path == RoutingPath.GREETING_PATH, (
        f"Query {query!r} should route to GREETING_PATH, got {decision.path}"
    )
    assert decision.has_case_state is False
    assert decision.interaction_class == "GREETING"


def test_greeting_bypasses_llm_entirely():
    """Greeting queries must not call the routing LLM at all."""
    call_count = []
    original_mock = _rule_based_routing

    def counting_mock(user_input: str) -> str:
        call_count.append(user_input)
        return original_mock(user_input)

    with patch("app.agent.runtime.interaction_policy._call_routing_llm", counting_mock):
        decision = evaluate_policy("Hallo!")

    assert decision.path == RoutingPath.GREETING_PATH
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
    assert decision.path != RoutingPath.GREETING_PATH, (
        f"Query {query!r} has technical content and must NOT route to GREETING_PATH"
    )
