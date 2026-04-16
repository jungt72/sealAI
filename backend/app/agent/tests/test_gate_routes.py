"""W1.4 — Tests fuer die umbenannten Gate-Routen.

Prueft dass:
  - Gate "CONVERSATION" zurueckgibt (nicht "instant_light_reply")
  - Gate "EXPLORATION" zurueckgibt (nicht "light_exploration")
  - Gate "GOVERNED" zurueckgibt (nicht "governed_needed")
  - ROUTE_ALIASES korrekte Mappings enthaelt
  - FrontdoorRoute Literal korrekte Werte enthaelt
  - Keine alten Route-Namen mehr in produktivem Code vorkommen
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent.runtime.gate import (
    ROUTE_ALIASES,
    FrontdoorRoute,
    GateDecision,
    LLMGateResult,
    _apply_llm_result,
    check_hard_overrides,
    classify_light_route,
    decide_route,
    _GOVERNED_LIGHT_THRESHOLD,
)


class _Session:
    def __init__(self, zone: str = "conversation"):
        self.session_zone = zone


CONV = _Session("conversation")
GOV = _Session("governed")


# ── Neue Routen-Namen ────────────────────────────────────────────────────────


class TestNewRouteNames:
    def test_greeting_returns_CONVERSATION(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Hallo", CONV)
        mock_llm.assert_not_called()
        assert decision.route == "CONVERSATION"

    def test_meta_returns_CONVERSATION(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Wie gehen wir dabei vor?", CONV)
        mock_llm.assert_not_called()
        assert decision.route == "CONVERSATION"

    def test_problem_returns_EXPLORATION(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Wir haben immer wieder Leckageprobleme.", CONV)
        mock_llm.assert_not_called()
        assert decision.route == "EXPLORATION"

    def test_uncertainty_returns_EXPLORATION(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Ich bin unsicher, welche Richtung sinnvoll ist.", CONV)
        mock_llm.assert_not_called()
        assert decision.route == "EXPLORATION"

    def test_numeric_param_returns_GOVERNED(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("PTFE-Dichtung fuer 180°C Dampf", CONV)
        mock_llm.assert_not_called()
        assert decision.route == "GOVERNED"

    def test_rfq_returns_GOVERNED(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Ich moechte ein Angebot anfordern", CONV)
        mock_llm.assert_not_called()
        assert decision.route == "GOVERNED"

    def test_matching_returns_GOVERNED(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Welche Hersteller liefern FKM-Dichtungen?", CONV)
        mock_llm.assert_not_called()
        assert decision.route == "GOVERNED"

    def test_llm_CONVERSATION_result_passes_through(self):
        llm_result = LLMGateResult(route="CONVERSATION", confidence=0.90)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Nur kurz bitte.", CONV)
        assert decision.route == "CONVERSATION"

    def test_llm_EXPLORATION_result_passes_through(self):
        llm_result = LLMGateResult(route="EXPLORATION", confidence=0.88)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Ich suche etwas fuer meine Pumpe.", CONV)
        assert decision.route == "EXPLORATION"

    def test_llm_GOVERNED_result_passes_through(self):
        llm_result = LLMGateResult(route="GOVERNED", confidence=0.97)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Etwas technisches.", CONV)
        assert decision.route == "GOVERNED"


# ── Alte Namen duerfen NICHT mehr zurueckkommen ───────────────────────────────


class TestNoOldRouteNames:
    OLD_NAMES = {"instant_light_reply", "light_exploration", "governed_needed"}

    def test_greeting_not_old_name(self):
        with patch("app.agent.runtime.gate._call_gate_llm"):
            decision = decide_route("Hallo", CONV)
        assert decision.route not in self.OLD_NAMES

    def test_problem_not_old_name(self):
        with patch("app.agent.runtime.gate._call_gate_llm"):
            decision = decide_route("Wir haben Leckageprobleme.", CONV)
        assert decision.route not in self.OLD_NAMES

    def test_numeric_not_old_name(self):
        with patch("app.agent.runtime.gate._call_gate_llm"):
            decision = decide_route("50 bar, 120 mm Welle", CONV)
        assert decision.route not in self.OLD_NAMES

    def test_parse_error_not_old_name(self):
        llm_result = LLMGateResult(route="GOVERNED", confidence=0.0, parse_error=True)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Irgendwas", CONV)
        assert decision.route not in self.OLD_NAMES

    def test_low_confidence_not_old_name(self):
        llm_result = LLMGateResult(route="EXPLORATION", confidence=0.50)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Mehrdeutig?", CONV)
        assert decision.route not in self.OLD_NAMES

    def test_classify_light_route_not_old_name(self):
        for msg in ["Hallo", "Wir haben Probleme.", "Ich bin unsicher."]:
            result = classify_light_route(msg)
            if result is not None:
                assert result.route not in self.OLD_NAMES, (
                    f"classify_light_route('{msg}') gab alten Namen '{result.route}' zurueck"
                )

    def test_apply_llm_result_not_old_name(self):
        for old_name in ["CONVERSATION", "EXPLORATION", "GOVERNED"]:
            result = LLMGateResult(route=old_name, confidence=0.95)  # type: ignore[arg-type]
            decision = _apply_llm_result(result, "test")
            assert decision.route not in self.OLD_NAMES


# ── ROUTE_ALIASES ────────────────────────────────────────────────────────────


class TestRouteAliases:
    def test_aliases_maps_old_to_new(self):
        assert ROUTE_ALIASES["instant_light_reply"] == "CONVERSATION"
        assert ROUTE_ALIASES["light_exploration"] == "EXPLORATION"
        assert ROUTE_ALIASES["governed_needed"] == "GOVERNED"

    def test_aliases_values_are_valid_routes(self):
        valid = {"CONVERSATION", "EXPLORATION", "GOVERNED"}
        for old_name, new_name in ROUTE_ALIASES.items():
            assert new_name in valid, (
                f"ROUTE_ALIASES['{old_name}'] = '{new_name}' ist kein gueltiger Route-Name"
            )

    def test_aliases_covers_all_three_old_names(self):
        assert set(ROUTE_ALIASES.keys()) == {
            "instant_light_reply",
            "light_exploration",
            "governed_needed",
        }

    def test_aliases_lookup_by_old_name(self):
        for old_name in ("instant_light_reply", "light_exploration", "governed_needed"):
            assert old_name in ROUTE_ALIASES, f"'{old_name}' fehlt in ROUTE_ALIASES"


# ── FrontdoorRoute Literal ────────────────────────────────────────────────────


class TestFrontdoorRouteLiteral:
    def test_new_names_are_valid_routes(self):
        # Literal-Type-Check via get_args
        import typing
        args = typing.get_args(FrontdoorRoute)
        assert "CONVERSATION" in args
        assert "EXPLORATION" in args
        assert "GOVERNED" in args

    def test_old_names_not_in_literal(self):
        import typing
        args = typing.get_args(FrontdoorRoute)
        assert "instant_light_reply" not in args
        assert "light_exploration" not in args
        assert "governed_needed" not in args

    def test_exactly_three_routes(self):
        import typing
        args = typing.get_args(FrontdoorRoute)
        assert len(args) == 3


# ── Governed-Session mit neuen Namen ─────────────────────────────────────────


class TestGovernedSessionNewNames:
    def test_governed_session_hard_override_returns_GOVERNED(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("PTFE fuer 180°C, 12 bar", GOV)
        mock_llm.assert_not_called()
        assert decision.route == "GOVERNED"

    def test_governed_session_greeting_returns_CONVERSATION(self):
        with patch("app.agent.runtime.gate._call_gate_llm") as mock_llm:
            decision = decide_route("Hallo", GOV)
        mock_llm.assert_not_called()
        assert decision.route == "CONVERSATION"
        assert decision.reason == "governed_instant_override"

    def test_governed_session_light_override_returns_EXPLORATION(self):
        llm_result = LLMGateResult(route="EXPLORATION", confidence=_GOVERNED_LIGHT_THRESHOLD)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Nur kurz.", GOV)
        assert decision.route == "EXPLORATION"
        assert decision.reason == "governed_light_override"

    def test_governed_session_parse_error_returns_GOVERNED(self):
        llm_result = LLMGateResult(route="GOVERNED", confidence=0.0, parse_error=True)
        with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result):
            decision = decide_route("Verstehe.", GOV)
        assert decision.route == "GOVERNED"
        assert decision.reason == "sticky_governed_session"
