"""
Tests for runtime/gate.py — Frontdoor 3-mode routing

Covers all cases from Umbauplan F-A.1:
  test_gate_hard_override_numeric_params  → governed_needed
  test_gate_hard_override_calculation     → governed_needed
  test_gate_greeting_routes_instant       → instant_light_reply
  test_gate_problem_routes_light          → light_exploration
  test_gate_ambiguous_question            → governed_needed (confidence < 0.75)
  test_gate_sticky_session                → governed_needed unless clearly light
  test_gate_llm_parse_error               → governed_needed
  test_gate_timeout_with_signal           → governed_needed
  test_gate_timeout_without_signal        → governed_needed

All LLM calls are mocked — no network I/O.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.agent.runtime.gate import (
    GateDecision,
    LLMGateResult,
    _GOVERNED_LIGHT_THRESHOLD,
    check_hard_overrides,
    classify_light_route,
    decide_route,
    _apply_llm_result,
)


# ---------------------------------------------------------------------------
# Minimal session stub
# ---------------------------------------------------------------------------

class _Session:
    def __init__(self, zone: str = "conversation"):
        self.session_zone = zone


CONV_SESSION = _Session("conversation")
GOV_SESSION = _Session("governed")


# ---------------------------------------------------------------------------
# check_hard_overrides (deterministic, no mocking needed)
# ---------------------------------------------------------------------------

class TestCheckHardOverrides:
    def test_numeric_celsius(self):
        result = check_hard_overrides("PTFE-Dichtung für 180°C Dampf")
        assert result is not None
        assert result.trigger == "numeric_unit"

    def test_numeric_bar(self):
        result = check_hard_overrides("Betriebsdruck 50 bar")
        assert result is not None
        assert result.trigger == "numeric_unit"

    def test_numeric_mm(self):
        result = check_hard_overrides("Wellendurchmesser 35 mm")
        assert result is not None
        assert result.trigger == "numeric_unit"

    def test_diameter_symbol(self):
        result = check_hard_overrides("Ø 35mm Welle")
        assert result is not None
        assert result.trigger in ("diameter", "numeric_unit")

    def test_calculation_rwdr(self):
        # "3000 rpm" hits numeric_unit first; both triggers are valid GOVERNED signals
        result = check_hard_overrides("RWDR für 3000 rpm berechnen")
        assert result is not None
        assert result.trigger in ("numeric_unit", "calculation")

    def test_calculation_keyword(self):
        result = check_hard_overrides("Bitte berechne die Grenzgeschwindigkeit")
        assert result is not None
        assert result.trigger == "calculation"

    def test_matching_hersteller(self):
        result = check_hard_overrides("Welche Hersteller liefern das?")
        assert result is not None
        assert result.trigger == "matching"

    def test_matching_wer_liefert(self):
        result = check_hard_overrides("Wer liefert FKM-Dichtungen?")
        assert result is not None
        assert result.trigger == "matching"

    def test_rfq_angebot(self):
        result = check_hard_overrides("Ich möchte ein Angebot anfordern")
        assert result is not None
        assert result.trigger == "rfq"

    def test_rfq_bestellen(self):
        result = check_hard_overrides("Kann ich das bestellen?")
        assert result is not None
        assert result.trigger == "rfq"

    def test_recommendation_intent(self):
        result = check_hard_overrides("Welche Dichtung sollen wir nehmen?")
        assert result is not None
        assert result.trigger == "recommendation"

    def test_correction_intent(self):
        result = check_hard_overrides("Korrigiere den Betriebsdruck, das stimmt nicht.")
        assert result is not None
        assert result.trigger == "correction"

    def test_ambiguity_intent(self):
        result = check_hard_overrides("Die Angaben sind widersprüchlich und mehrdeutig.")
        assert result is not None
        assert result.trigger in ("ambiguity", "correction")

    def test_trivial_greeting_no_override(self):
        result = check_hard_overrides("Hallo, wie geht es dir?")
        assert result is None

    def test_knowledge_question_no_override(self):
        result = check_hard_overrides("Was ist ein O-Ring?")
        assert result is None

    def test_general_knowledge_no_override(self):
        result = check_hard_overrides("Erkläre mir den Unterschied zwischen FKM und NBR")
        assert result is None


# ---------------------------------------------------------------------------
# _apply_llm_result (unit tests for the decision mapping logic)
# ---------------------------------------------------------------------------

class TestApplyLLMResult:
    def test_parse_error_yields_governed(self):
        result = LLMGateResult(routing="governed_needed", confidence=0.0, parse_error=True)
        decision = _apply_llm_result(result, "irrelevant")
        assert decision.route == "governed_needed"
        assert decision.reason == "json_parse_fallback"

    def test_low_confidence_yields_governed(self):
        result = LLMGateResult(routing="light_exploration", confidence=0.60)
        decision = _apply_llm_result(result, "mehrdeutige Frage")
        assert decision.route == "governed_needed"
        assert decision.reason == "low_confidence_fallback"

    def test_confidence_exactly_at_threshold_passes(self):
        # 0.75 is the boundary — exactly at threshold is NOT low confidence
        result = LLMGateResult(routing="instant_light_reply", confidence=0.75)
        decision = _apply_llm_result(result, "Was ist ein O-Ring?")
        assert decision.route == "instant_light_reply"
        assert decision.reason == "llm_frontdoor_classification"

    def test_high_confidence_instant_light(self):
        result = LLMGateResult(routing="instant_light_reply", confidence=0.92)
        decision = _apply_llm_result(result, "Was ist ein O-Ring?")
        assert decision.route == "instant_light_reply"
        assert decision.reason == "llm_frontdoor_classification"

    def test_high_confidence_governed(self):
        result = LLMGateResult(routing="governed_needed", confidence=0.95)
        decision = _apply_llm_result(result, "PTFE für 180°C")
        assert decision.route == "governed_needed"
        assert decision.reason == "llm_frontdoor_classification"

    def test_timeout_with_deterministic_signal(self):
        # timeout flag set, but message has a hard override signal
        result = LLMGateResult(routing="instant_light_reply", confidence=0.0, timeout=True)
        decision = _apply_llm_result(result, "berechne Grenzgeschwindigkeit")
        assert decision.route == "governed_needed"
        assert "timeout_with_deterministic_signal" in decision.reason

    def test_timeout_without_signal_falls_back_to_governed(self):
        result = LLMGateResult(routing="instant_light_reply", confidence=0.0, timeout=True)
        decision = _apply_llm_result(result, "Was ist ein O-Ring?")
        assert decision.route == "governed_needed"
        assert decision.reason == "timeout_fallback_to_governed"


class TestClassifyLightRoute:
    def test_greeting_routes_to_instant(self):
        decision = classify_light_route("Hallo")
        assert decision is not None
        assert decision.route == "instant_light_reply"

    def test_meta_question_routes_to_instant(self):
        decision = classify_light_route("Wie funktioniert das bei euch?")
        assert decision is not None
        assert decision.route == "instant_light_reply"

    def test_problem_routes_to_light_exploration(self):
        decision = classify_light_route("Wir haben immer wieder Leckageprobleme.")
        assert decision is not None
        assert decision.route == "light_exploration"

    def test_uncertainty_routes_to_light_exploration(self):
        decision = classify_light_route("Ich bin unsicher, wie wir das angehen sollen.")
        assert decision is not None
        assert decision.route == "light_exploration"


# ---------------------------------------------------------------------------
# decide_route integration tests (LLM mocked)
# ---------------------------------------------------------------------------

class TestDecideRoute:
    # ── Hard override cases ────────────────────────────────────────────────

    def test_gate_hard_override_numeric_params(self):
        """Numeric unit triggers GOVERNED without any LLM call."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("PTFE-Dichtung für 180°C Dampf", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"
        assert "numeric_unit" in decision.reason

    def test_gate_hard_override_calculation(self):
        """Calculation keyword triggers GOVERNED without any LLM call."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Bitte berechne den RWDR für 3000 rpm", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"

    def test_gate_hard_override_matching(self):
        """Manufacturer/matching trigger → GOVERNED, no LLM."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Welche Hersteller liefern FKM-Dichtungen?", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"

    def test_gate_hard_override_rfq(self):
        """RFQ trigger → GOVERNED, no LLM."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Ich möchte ein Angebot anfordern", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"

    # ── Deterministic light modes ─────────────────────────────────────────

    def test_gate_greeting_routes_to_instant_light_reply(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Hallo", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "instant_light_reply"

    def test_gate_meta_question_routes_to_instant_light_reply(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Wie gehen wir dabei vor?", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "instant_light_reply"

    def test_gate_problem_statement_routes_to_light_exploration(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Wir haben immer wieder Leckageprobleme.", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "light_exploration"

    def test_gate_uncertainty_routes_to_light_exploration(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Ich bin unsicher, welche Richtung sinnvoll ist.", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "light_exploration"

    # ── Ambiguous / low-confidence ─────────────────────────────────────────

    def test_gate_ambiguous_question(self):
        """LLM returns light mode but with low confidence → governed_needed."""
        llm_result = LLMGateResult(routing="light_exploration", confidence=0.60)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Irgendwas mit Dichtung?", CONV_SESSION)
        assert decision.route == "governed_needed"
        assert decision.reason == "low_confidence_fallback"

    # ── Governed session — technical triggers ─────────────────────────────

    def test_gate_governed_session_hard_override_stays_governed_no_llm(self):
        """Governed session + hard override → GOVERNED immediately, LLM not called."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("PTFE-Dichtung für 180°C Dampf, 12 bar", GOV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"
        assert "hard_override" in decision.reason

    def test_gate_governed_session_calculation_stays_governed_no_llm(self):
        """Governed session + calculation keyword → GOVERNED, LLM not called."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Berechne den RWDR für diese Welle", GOV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"

    def test_gate_governed_session_matching_stays_governed_no_llm(self):
        """Governed session + manufacturer query → GOVERNED, LLM not called."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Welche Hersteller liefern das?", GOV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"

    # ── Governed session — light override ─────────────────────────────────

    def test_gate_governed_session_calls_llm_for_non_technical_message(self):
        """Governed session without hard override → LLM IS consulted."""
        llm_result = LLMGateResult(routing="governed_needed", confidence=0.70)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result) as mock_llm:
            decide_route("Verstehe.", GOV_SESSION)
        mock_llm.assert_called_once()

    def test_gate_governed_session_instant_override_without_llm(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Hallo", GOV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "instant_light_reply"
        assert decision.reason == "governed_instant_override"

    def test_gate_governed_session_light_override(self):
        """Governed session + clear non-technical light turn → light mode."""
        llm_result = LLMGateResult(routing="light_exploration", confidence=_GOVERNED_LIGHT_THRESHOLD)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Nur kurz ohne Technik.", GOV_SESSION)
        assert decision.route == "light_exploration"
        assert decision.reason == "governed_light_override"

    def test_gate_governed_session_instant_override_high_confidence(self):
        """Governed session + clearly harmless meta/smalltalk → instant mode."""
        llm_result = LLMGateResult(routing="instant_light_reply", confidence=0.90)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Nur kurz ohne Technik.", GOV_SESSION)
        assert decision.route == "instant_light_reply"
        assert decision.reason == "governed_light_override"

    def test_gate_governed_session_borderline_confidence_stays_governed(self):
        """Governed session + light mode below threshold → governed_needed."""
        below = _GOVERNED_LIGHT_THRESHOLD - 0.01
        llm_result = LLMGateResult(routing="light_exploration", confidence=below)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Irgendwas unklar?", GOV_SESSION)
        assert decision.route == "governed_needed"
        assert decision.reason == "sticky_governed_session"

    def test_gate_governed_session_llm_says_governed_stays_governed(self):
        """Governed session + LLM still says GOVERNED → GOVERNED (sticky).

        Uses a message without numeric units so the hard-override path is
        bypassed and the LLM path is exercised.
        """
        llm_result = LLMGateResult(routing="governed_needed", confidence=0.95)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Ich habe dazu noch eine Frage.", GOV_SESSION)
        assert decision.route == "governed_needed"
        assert decision.reason == "sticky_governed_session"

    def test_gate_governed_session_llm_failure_stays_governed(self):
        """Governed session + LLM error → GOVERNED (fail-safe)."""
        with patch("app.agent.runtime.gate._call_gate_llm", side_effect=TimeoutError("timeout")):
            decision = decide_route("Verstehe.", GOV_SESSION)
        assert decision.route == "governed_needed"
        assert decision.reason == "sticky_governed_session"

    def test_gate_governed_session_llm_parse_error_stays_governed(self):
        """Governed session + LLM parse error → GOVERNED."""
        llm_result = LLMGateResult(routing="governed_needed", confidence=0.0, parse_error=True)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Verstehe.", GOV_SESSION)
        assert decision.route == "governed_needed"
        assert decision.reason == "sticky_governed_session"

    # ── LLM error cases ────────────────────────────────────────────────────

    def test_gate_llm_parse_error(self):
        """LLM returns unparseable JSON → governed_needed."""
        llm_result = LLMGateResult(routing="governed_needed", confidence=0.0, parse_error=True)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Irgendeine Nachricht", CONV_SESSION)
        assert decision.route == "governed_needed"
        assert decision.reason == "json_parse_fallback"

    def test_gate_llm_exception_with_hard_override_message(self):
        """If message has a hard override signal, LLM is never called — caught at step 2."""
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("berechne Grenzgeschwindigkeit", CONV_SESSION)
        mock_llm.assert_not_called()
        assert decision.route == "governed_needed"
        assert decision.reason == "hard_override:calculation"

    def test_gate_timeout_with_signal(self):
        """LLM result has timeout=True + message re-checked has deterministic signal.

        This case is covered at unit level by TestApplyLLMResult.test_timeout_with_signal.
        In decide_route, messages with hard overrides are caught at step 2 before the LLM.
        Here we verify the unit-level path via _apply_llm_result directly.
        """
        from app.agent.runtime.gate import _apply_llm_result
        result = LLMGateResult(routing="instant_light_reply", confidence=0.0, timeout=True)
        decision = _apply_llm_result(result, "RWDR berechnen bitte")
        assert decision.route == "governed_needed"
        assert "timeout_with_deterministic_signal" in decision.reason

    def test_gate_timeout_without_signal(self):
        """LLM raises exception, no deterministic signal → governed_needed."""
        with patch(
            "app.agent.runtime.gate._call_gate_llm",
            side_effect=TimeoutError("timeout"),
        ):
            decision = decide_route("Verstehe.", CONV_SESSION)
        assert decision.route == "governed_needed"
        assert decision.reason == "timeout_fallback_to_governed"

    def test_gate_llm_network_error_falls_back(self):
        """Any LLM exception without hard signal → governed_needed fallback."""
        with patch(
            "app.agent.runtime.gate._call_gate_llm",
            side_effect=ConnectionError("network error"),
        ):
            decision = decide_route("Hallo, wie geht es dir?", CONV_SESSION)
        assert decision.route == "governed_needed"


# ---------------------------------------------------------------------------
# GateDecision contract
# ---------------------------------------------------------------------------

class TestGateDecisionContract:
    def test_route_is_three_mode(self):
        d = GateDecision(route="governed_needed", reason="test")
        assert d.route in ("instant_light_reply", "light_exploration", "governed_needed")

    def test_decision_is_frozen(self):
        d = GateDecision(route="instant_light_reply", reason="test")
        with pytest.raises((AttributeError, TypeError)):
            d.route = "governed_needed"  # type: ignore[misc]
