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

from app.agent.runtime.interaction_policy import (
    _check_input_blocked,
    _is_meta_query,
    _fast_path_upgrade_to_structured,
)
from app.domain.pre_gate_classification import PreGateClassification


# ---------------------------------------------------------------------------
# 1. Blocked path — deterministic pre-check
# ---------------------------------------------------------------------------


class TestBlockedPreCheck:
    @pytest.mark.parametrize(
        "text",
        [
            "Welchen Hersteller soll ich nehmen?",
            "Bitte eine Herstellerempfehlung für Dichtringe",
            "empfiehl mir ein Produkt",
            "was empfiehlst du mir für diese Anwendung?",
            "Welches Material soll ich verwenden?",
            "Welche Dichtung soll ich einbauen?",
        ],
    )
    def test_blocked_inputs_detected(self, text):
        reason = _check_input_blocked(text)
        assert reason is not None, f"Expected blocked, got None for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "Was ist FKM?",
            "Hallo, kannst du mir helfen?",
            "Meine Welle hat 50mm Durchmesser",
            "Betriebsdruck 5 bar, Medium: Wasser",
            "Welche Parameter brauche ich noch?",
            "Wie hoch ist der pv-Wert bei diesen Bedingungen?",
        ],
    )
    def test_safe_inputs_not_blocked(self, text):
        reason = _check_input_blocked(text)
        assert (
            reason is None
        ), f"Expected not blocked, got reason={reason!r} for: {text!r}"

    def test_block_reason_is_nonempty_string(self):
        reason = _check_input_blocked("Welchen Hersteller soll ich nehmen?")
        assert isinstance(reason, str) and len(reason) > 0


# ---------------------------------------------------------------------------
# 2. Meta path — deterministic pre-check
# ---------------------------------------------------------------------------


class TestMetaPreCheck:
    @pytest.mark.parametrize(
        "text",
        [
            "Was fehlt noch?",
            "Welche Parameter brauche ich noch?",
            "Wie ist der aktuelle Stand?",
            "Was hast du schon verstanden?",
            "Zeig mir den Fortschritt",
            "Zeig mir den Fortschritt",
            "Was fehlt",
            "Was hast du bisher erfasst?",
        ],
    )
    def test_meta_queries_detected(self, text):
        assert _is_meta_query(text) is True, f"Expected meta, got False for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "Welle 50mm, 3000 rpm, Öl, 5 bar",
            "Was ist FKM?",
            "Welchen Hersteller soll ich nehmen?",
            "Hallo!",
            "Bitte erkläre mir den pv-Wert",
        ],
    )
    def test_non_meta_not_detected(self, text):
        assert (
            _is_meta_query(text) is False
        ), f"Expected not meta, got True for: {text!r}"


# ---------------------------------------------------------------------------
# 3. Fast path upgrade — technical specificity → structured
# ---------------------------------------------------------------------------


class TestFastPathUpgrade:
    @pytest.mark.parametrize(
        "text",
        [
            "50 mm Welle, 3000 rpm",
            "Druck ist 5 bar",
            "Temperatur 80°C",
            "Durchmesser 40mm",
            "FKM für aggressive Medien",
            "NBR bei hohen Temperaturen",
            "PTFE in Säure verwenden",
        ],
    )
    def test_technical_inputs_trigger_upgrade(self, text):
        assert (
            _fast_path_upgrade_to_structured(text) is True
        ), f"Expected upgrade to structured, got False for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "Hallo, wie geht es dir?",
            "Was ist ein Radialwellendichtring?",
            "Danke für deine Hilfe",
            "Bitte erkläre mir FKM",
            "Wer bist du?",
        ],
    )
    def test_safe_fast_inputs_not_upgraded(self, text):
        assert (
            _fast_path_upgrade_to_structured(text) is False
        ), f"Expected no upgrade, got True for: {text!r}"


# ---------------------------------------------------------------------------
# 4. PreGateClassification enum completeness
# ---------------------------------------------------------------------------


class TestPreGateClassificationEnum:
    def test_all_five_classifications_exist(self):
        assert PreGateClassification.GREETING.value == "GREETING"
        assert PreGateClassification.META_QUESTION.value == "META_QUESTION"
        assert PreGateClassification.KNOWLEDGE_QUERY.value == "KNOWLEDGE_QUERY"
        assert PreGateClassification.BLOCKED.value == "BLOCKED"
        assert PreGateClassification.DOMAIN_INQUIRY.value == "DOMAIN_INQUIRY"

    def test_blocked_classification_is_string_enum(self):
        assert isinstance(PreGateClassification.BLOCKED, str)
        assert PreGateClassification.BLOCKED == "BLOCKED"


# ---------------------------------------------------------------------------
# 5. evaluate_policy integration — pre-checks applied correctly
# ---------------------------------------------------------------------------


class TestEvaluatePolicyPreChecks:
    def test_meta_query_returns_meta_path_without_llm(self, monkeypatch):
        """Meta queries must not reach the LLM routing call."""
        import app.agent.runtime.interaction_policy as ip_mod

        called = []
        monkeypatch.setattr(
            ip_mod, "_call_routing_llm", lambda x: called.append(x) or "Fast"
        )

        decision = ip_mod.evaluate_policy("Was fehlt noch?")
        assert decision.pre_gate_classification is PreGateClassification.META_QUESTION
        assert decision.path == "meta"
        assert called == [], "LLM must not be called for meta queries"

    def test_blocked_query_returns_blocked_path_without_llm(self, monkeypatch):
        """Blocked queries must not reach the LLM routing call."""
        import app.agent.runtime.interaction_policy as ip_mod

        called = []
        monkeypatch.setattr(
            ip_mod, "_call_routing_llm", lambda x: called.append(x) or "Fast"
        )

        decision = ip_mod.evaluate_policy("Welchen Hersteller soll ich nehmen?")
        assert decision.pre_gate_classification is PreGateClassification.BLOCKED
        assert decision.path == "blocked"
        assert called == [], "LLM must not be called for blocked queries"

    def test_technical_fast_is_upgraded_to_structured(self, monkeypatch):
        """Fast LLM decision for technical input must be upgraded to Structured."""
        import app.agent.runtime.interaction_policy as ip_mod

        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: "Fast")

        decision = ip_mod.evaluate_policy("Druck 5 bar, Temperatur 80°C")
        assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
        assert decision.path == "structured"

    def test_clean_fast_stays_fast(self, monkeypatch):
        """Harmless greeting classified as Fast by LLM must stay on fast path."""
        import app.agent.runtime.interaction_policy as ip_mod

        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: "Fast")

        decision = ip_mod.evaluate_policy("Hallo, wer bist du?")
        assert decision.pre_gate_classification is PreGateClassification.META_QUESTION
        assert decision.path == "meta"

    def test_llm_error_falls_back_to_structured(self, monkeypatch):
        """LLM failure must fall back to Structured, never to Fast or Blocked."""
        import app.agent.runtime.interaction_policy as ip_mod

        monkeypatch.setattr(
            ip_mod,
            "_call_routing_llm",
            lambda x: (_ for _ in ()).throw(RuntimeError("network error")),
        )

        decision = ip_mod.evaluate_policy("Ich habe eine Dichtefrage")
        assert decision.pre_gate_classification is PreGateClassification.DOMAIN_INQUIRY
        assert decision.path == "structured"

    def test_blocked_decision_has_escalation_reason(self, monkeypatch):
        """Blocked decision must carry a non-empty escalation_reason."""
        import app.agent.runtime.interaction_policy as ip_mod

        monkeypatch.setattr(ip_mod, "_call_routing_llm", lambda x: "Fast")

        decision = ip_mod.evaluate_policy("Welchen Hersteller soll ich nehmen?")
        assert decision.pre_gate_classification is PreGateClassification.BLOCKED
        assert decision.path == "blocked"
        assert decision.escalation_reason is not None
        assert len(decision.escalation_reason) > 0


# ---------------------------------------------------------------------------
# 6. Fast responder service: blocked and meta frontdoor responses
# ---------------------------------------------------------------------------


class TestBlockedAndMetaNodes:
    def _respond(self, text: str, classification: PreGateClassification):
        from app.services.fast_responder_service import FastResponderService

        return FastResponderService().respond(text, classification)

    def test_blocked_node_returns_message(self):
        result = self._respond(
            "Welchen Hersteller soll ich nehmen?",
            PreGateClassification.BLOCKED,
        )
        content = result.content
        assert len(content) > 0
        assert result.no_case_created is True
        assert result.source_classification is PreGateClassification.BLOCKED
        # Must NOT contain manufacturer names or material recommendations
        assert "Freudenberg" not in content
        assert "FKM" not in content

    def test_blocked_node_content_is_deterministic(self):
        r1 = self._respond(
            "Welchen Hersteller soll ich nehmen?",
            PreGateClassification.BLOCKED,
        ).content
        r2 = self._respond(
            "Welchen Hersteller soll ich nehmen?",
            PreGateClassification.BLOCKED,
        ).content
        assert r1 == r2

    def test_meta_node_returns_platform_status_response(self):
        result = self._respond(
            "Was fehlt noch?",
            PreGateClassification.META_QUESTION,
        )
        content = result.content
        assert "SeaLAI" in content
        assert result.no_case_created is True
        assert result.source_classification is PreGateClassification.META_QUESTION

    def test_meta_node_exposes_registration_prompt(self):
        result = self._respond(
            "Wie ist der aktuelle Stand?",
            PreGateClassification.META_QUESTION,
        )
        assert result.registration_prompt is not None
        assert (
            result.registration_prompt.reason == "case_creation_requires_registration"
        )

    def test_meta_node_does_not_read_working_profile(self):
        """Fast responder has no engineering state input and cannot surface draft values."""
        result = self._respond(
            "Was hast du bisher erfasst?",
            PreGateClassification.META_QUESTION,
        )
        content = result.content
        assert "Öl" not in content
        assert "3.0" not in content

    def test_route_by_policy_blocked(self):
        from app.agent.runtime.policy import legacy_policy_path_for_pre_gate

        assert (
            legacy_policy_path_for_pre_gate(PreGateClassification.BLOCKED) == "blocked"
        )

    def test_route_by_policy_meta(self):
        from app.agent.runtime.policy import legacy_policy_path_for_pre_gate

        assert (
            legacy_policy_path_for_pre_gate(PreGateClassification.META_QUESTION)
            == "meta"
        )

    def test_route_by_policy_fast(self):
        from app.agent.runtime.policy import legacy_policy_path_for_pre_gate

        assert (
            legacy_policy_path_for_pre_gate(PreGateClassification.GREETING)
            == "greeting"
        )

    def test_route_by_policy_structured_default(self):
        from app.agent.runtime.policy import legacy_policy_path_for_pre_gate

        assert (
            legacy_policy_path_for_pre_gate(PreGateClassification.DOMAIN_INQUIRY)
            == "structured"
        )

    def test_route_by_policy_knowledge_uses_fast_path(self):
        from app.agent.runtime.policy import legacy_policy_path_for_pre_gate

        assert (
            legacy_policy_path_for_pre_gate(PreGateClassification.KNOWLEDGE_QUERY)
            == "fast"
        )
