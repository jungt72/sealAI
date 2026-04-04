"""
Tests for Phase 0D — Interaction Policy hardening.

Covers:
1. PATCH 1 — Blocked path (explicitly forbidden requests)
2. PATCH 1 — Meta path (state-status queries)
3. PATCH 2 — Fast path technical-specificity upgrade to structured
4. PATCH 1 — Routing path enum completeness
5. blocked_node and meta_response_node in graph.py
"""
from __future__ import annotations

import pytest

from app.agent.agent.policy import RoutingPath, ResultForm
from app.agent.agent.interaction_policy import (
    _check_input_blocked,
    _is_meta_query,
    _fast_path_upgrade_to_structured,
)


# ---------------------------------------------------------------------------
# 1. Blocked path — deterministic pre-check
# ---------------------------------------------------------------------------

class TestBlockedPreCheck:
    @pytest.mark.parametrize("text", [
        "Welchen Hersteller soll ich nehmen?",
        "Bitte eine Herstellerempfehlung für Dichtringe",
        "empfiehl mir ein Produkt",
        "was empfiehlst du mir für diese Anwendung?",
        "Welches Material soll ich verwenden?",
        "Welche Dichtung soll ich einbauen?",
    ])
    def test_blocked_inputs_detected(self, text):
        reason = _check_input_blocked(text)
        assert reason is not None, f"Expected blocked, got None for: {text!r}"

    @pytest.mark.parametrize("text", [
        "Was ist FKM?",
        "Hallo, kannst du mir helfen?",
        "Meine Welle hat 50mm Durchmesser",
        "Betriebsdruck 5 bar, Medium: Wasser",
        "Welche Parameter brauche ich noch?",
        "Wie hoch ist der pv-Wert bei diesen Bedingungen?",
    ])
    def test_safe_inputs_not_blocked(self, text):
        reason = _check_input_blocked(text)
        assert reason is None, f"Expected not blocked, got reason={reason!r} for: {text!r}"

    def test_block_reason_is_nonempty_string(self):
        reason = _check_input_blocked("Welchen Hersteller soll ich nehmen?")
        assert isinstance(reason, str) and len(reason) > 0


# ---------------------------------------------------------------------------
# 2. Meta path — deterministic pre-check
# ---------------------------------------------------------------------------

class TestMetaPreCheck:
    @pytest.mark.parametrize("text", [
        "Was fehlt noch?",
        "Welche Parameter brauche ich noch?",
        "Wie ist der aktuelle Stand?",
        "Was hast du schon verstanden?",
        "Zeig mir den Fortschritt",
        "Zeig mir den Fortschritt",
        "Was fehlt",
        "Was hast du bisher erfasst?",
    ])
    def test_meta_queries_detected(self, text):
        assert _is_meta_query(text) is True, f"Expected meta, got False for: {text!r}"

    @pytest.mark.parametrize("text", [
        "Welle 50mm, 3000 rpm, Öl, 5 bar",
        "Was ist FKM?",
        "Welchen Hersteller soll ich nehmen?",
        "Hallo!",
        "Bitte erkläre mir den pv-Wert",
    ])
    def test_non_meta_not_detected(self, text):
        assert _is_meta_query(text) is False, f"Expected not meta, got True for: {text!r}"


# ---------------------------------------------------------------------------
# 3. Fast path upgrade — technical specificity → structured
# ---------------------------------------------------------------------------

class TestFastPathUpgrade:
    @pytest.mark.parametrize("text", [
        "50 mm Welle, 3000 rpm",
        "Druck ist 5 bar",
        "Temperatur 80°C",
        "Durchmesser 40mm",
        "FKM für aggressive Medien",
        "NBR bei hohen Temperaturen",
        "PTFE in Säure verwenden",
    ])
    def test_technical_inputs_trigger_upgrade(self, text):
        assert _fast_path_upgrade_to_structured(text) is True, (
            f"Expected upgrade to structured, got False for: {text!r}"
        )

    @pytest.mark.parametrize("text", [
        "Hallo, wie geht es dir?",
        "Was ist ein Radialwellendichtring?",
        "Danke für deine Hilfe",
        "Bitte erkläre mir FKM",
        "Wer bist du?",
    ])
    def test_safe_fast_inputs_not_upgraded(self, text):
        assert _fast_path_upgrade_to_structured(text) is False, (
            f"Expected no upgrade, got True for: {text!r}"
        )


# ---------------------------------------------------------------------------
# 4. RoutingPath enum completeness
# ---------------------------------------------------------------------------

class TestRoutingPathEnum:
    def test_all_four_paths_exist(self):
        assert RoutingPath.FAST_PATH.value == "fast"
        assert RoutingPath.STRUCTURED_PATH.value == "structured"
        assert RoutingPath.META_PATH.value == "meta"
        assert RoutingPath.BLOCKED_PATH.value == "blocked"

    def test_blocked_path_is_string_enum(self):
        assert isinstance(RoutingPath.BLOCKED_PATH, str)
        assert RoutingPath.BLOCKED_PATH == "blocked"


# ---------------------------------------------------------------------------
# 5. evaluate_policy integration — pre-checks applied correctly
# ---------------------------------------------------------------------------

class TestEvaluatePolicyPreChecks:
    def test_meta_query_returns_meta_path_without_llm(self, monkeypatch):
        """Meta queries must not reach the LLM routing call."""
        import app.agent.agent.interaction_policy as ip_mod
        called = []
        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: called.append(x) or "Fast")

        decision = ip_mod.evaluate_policy("Was fehlt noch?")
        assert decision.path == RoutingPath.META_PATH
        assert called == [], "LLM must not be called for meta queries"

    def test_blocked_query_returns_blocked_path_without_llm(self, monkeypatch):
        """Blocked queries must not reach the LLM routing call."""
        import app.agent.agent.interaction_policy as ip_mod
        called = []
        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: called.append(x) or "Fast")

        decision = ip_mod.evaluate_policy("Welchen Hersteller soll ich nehmen?")
        assert decision.path == RoutingPath.BLOCKED_PATH
        assert called == [], "LLM must not be called for blocked queries"

    def test_technical_fast_is_upgraded_to_structured(self, monkeypatch):
        """Fast LLM decision for technical input must be upgraded to Structured."""
        import app.agent.agent.interaction_policy as ip_mod
        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: "Fast")

        decision = ip_mod.evaluate_policy("Druck 5 bar, Temperatur 80°C")
        assert decision.path == RoutingPath.STRUCTURED_PATH

    def test_clean_fast_stays_fast(self, monkeypatch):
        """Harmless greeting classified as Fast by LLM must stay on fast path."""
        import app.agent.agent.interaction_policy as ip_mod
        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: "Fast")

        decision = ip_mod.evaluate_policy("Hallo, wer bist du?")
        assert decision.path == RoutingPath.FAST_PATH

    def test_llm_error_falls_back_to_structured(self, monkeypatch):
        """LLM failure must fall back to Structured, never to Fast or Blocked."""
        import app.agent.agent.interaction_policy as ip_mod
        monkeypatch.setattr(
            ip_mod, "_call_routing_llm",
            lambda x: (_ for _ in ()).throw(RuntimeError("network error"))
        )

        decision = ip_mod.evaluate_policy("Ich habe eine Dichtefrage")
        assert decision.path == RoutingPath.STRUCTURED_PATH

    def test_blocked_decision_has_escalation_reason(self, monkeypatch):
        """Blocked decision must carry a non-empty escalation_reason."""
        import app.agent.agent.interaction_policy as ip_mod
        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: "Fast")

        decision = ip_mod.evaluate_policy("Welchen Hersteller soll ich nehmen?")
        assert decision.path == RoutingPath.BLOCKED_PATH
        assert decision.escalation_reason is not None
        assert len(decision.escalation_reason) > 0


# ---------------------------------------------------------------------------
# 6. Graph nodes: blocked_node and meta_response_node
# ---------------------------------------------------------------------------

class TestBlockedAndMetaNodes:
    def _make_state(self, policy_path: str, sealing_state: dict | None = None) -> dict:
        from langchain_core.messages import HumanMessage
        return {
            "messages": [HumanMessage(content="test")],
            "sealing_state": sealing_state or {
                "observed": {}, "normalized": {}, "asserted": {},
                "governance": {}, "cycle": {},
            },
            "working_profile": {},
            "relevant_fact_cards": [],
            "tenant_id": "tenant_test",
            "turn_count": 0,
            "max_turns": 12,
            "policy_path": policy_path,
            "result_form": "direct_answer",
        }

    def test_blocked_node_returns_message(self):
        from app.agent.agent.graph import blocked_node
        from app.agent.agent.boundaries import FAST_PATH_DISCLAIMER

        state = self._make_state("blocked")
        result = blocked_node(state)
        content = result["messages"][0].content
        assert len(content) > 0
        assert FAST_PATH_DISCLAIMER in content
        # Must NOT contain manufacturer names or material recommendations
        assert "Freudenberg" not in content
        assert "FKM" not in content

    def test_blocked_node_content_is_deterministic(self):
        from app.agent.agent.graph import blocked_node

        state = self._make_state("blocked")
        r1 = blocked_node(state)["messages"][0].content
        r2 = blocked_node(state)["messages"][0].content
        assert r1 == r2

    def test_meta_node_empty_state_shows_all_missing(self):
        from app.agent.agent.graph import meta_response_node

        state = self._make_state("meta")
        result = meta_response_node(state)
        content = result["messages"][0].content
        assert "fehlend" in content.lower() or "fehlen" in content.lower()
        # No confirmed items
        assert "Bestätigte Angaben" not in content or "Noch keine" in content

    def test_meta_node_shows_confirmed_asserted_values(self):
        from app.agent.agent.graph import meta_response_node

        sealing_state = {
            "observed": {}, "normalized": {}, "governance": {}, "cycle": {},
            "asserted": {
                "medium_profile": {"name": "Wasser"},
                "operating_conditions": {"pressure": 5.0, "temperature": 80.0},
                "machine_profile": {},
            },
        }
        state = self._make_state("meta", sealing_state=sealing_state)
        result = meta_response_node(state)
        content = result["messages"][0].content
        assert "Wasser" in content
        assert "5.0" in content
        assert "80.0" in content

    def test_meta_node_does_not_read_working_profile(self):
        """working_profile values must NOT appear in meta response — only asserted."""
        from app.agent.agent.graph import meta_response_node

        # working_profile has a medium, asserted does not
        state = self._make_state("meta")
        state["working_profile"] = {"medium": "Öl", "pressure_bar": 3.0}
        # asserted is empty

        result = meta_response_node(state)
        content = result["messages"][0].content
        # Must NOT show "Öl" as confirmed (it's only in working_profile)
        assert "Bestätigte Angaben" not in content or "Öl" not in content

    def test_route_by_policy_blocked(self):
        from app.agent.agent.graph import route_by_policy
        from langchain_core.messages import HumanMessage

        state = self._make_state("blocked")
        assert route_by_policy(state) == "blocked_node"

    def test_route_by_policy_meta(self):
        from app.agent.agent.graph import route_by_policy

        state = self._make_state("meta")
        assert route_by_policy(state) == "meta_response_node"

    def test_route_by_policy_fast(self):
        from app.agent.agent.graph import route_by_policy

        state = self._make_state("fast")
        assert route_by_policy(state) == "fast_guidance_node"

    def test_route_by_policy_structured_default(self):
        from app.agent.agent.graph import route_by_policy

        state = self._make_state("structured")
        assert route_by_policy(state) == "reasoning_node"

    def test_route_by_policy_unknown_defaults_to_structured(self):
        from app.agent.agent.graph import route_by_policy

        state = self._make_state("unknown_future_path")
        assert route_by_policy(state) == "reasoning_node"
