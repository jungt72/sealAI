"""
Phase 0E — Patch 1: End-to-end path-proof for all 4 runtime paths.

Each test calls the compiled LangGraph app (app.ainvoke) with a real
policy_path injected into state, and verifies that the correct node
ran and the user-visible output is semantically correct.

LLM/RAG calls are mocked; the router, node logic, and boundary blocks
run real — this is an integration test, not an isolated unit test.

Covered paths:
  fast     → fast_guidance_node → END
  meta     → meta_response_node → END  (no LLM at all)
  blocked  → blocked_node       → END  (no LLM at all)
  structured → reasoning_node → selection_node → final_response_node → END
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.agent.boundaries import FAST_PATH_DISCLAIMER, STRUCTURED_PATH_SUFFIX
from app.agent.agent.graph import _BLOCKED_REFUSAL, app as compiled_graph
from app.agent.agent.output_guard import FAST_PATH_GUARD_FALLBACK


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_e2e_state(**overrides: Any) -> dict:
    """Minimal AgentState that can traverse all four graph paths."""
    base: dict[str, Any] = {
        "messages": [HumanMessage(content="Test message")],
        "sealing_state": {
            "observed": {"observed_inputs": [], "raw_parameters": {}},
            "normalized": {"identity_records": {}, "normalized_parameters": {}},
            "asserted": {
                "medium_profile": {},
                "machine_profile": {},
                "installation_profile": {},
                "operating_conditions": {},
                "sealing_requirement_spec": {},
            },
            "governance": {
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "scope_of_validity": [],
                "assumptions_active": [],
                "gate_failures": [],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": [],
                "conflicts": [],
            },
            "cycle": {
                "analysis_cycle_id": "e2e-test-1",
                "snapshot_parent_revision": 0,
                "superseded_by_cycle": None,
                "contract_obsolete": False,
                "contract_obsolete_reason": None,
                "state_revision": 1,
            },
            "selection": {
                "selection_status": "blocked_no_candidates",
                "candidates": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [],
                "winner_candidate_id": None,
                "recommendation_artifact": None,
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
            },
            "review": {},
            "handover": None,
        },
        "relevant_fact_cards": [],
        "working_profile": {},
        "tenant_id": "test-tenant",
        "run_meta": {},
    }
    base.update(overrides)
    return base


def _get_last_ai_message(state: dict) -> str:
    msgs = state.get("messages", [])
    for msg in reversed(msgs):
        if isinstance(msg, AIMessage):
            return msg.content
    return ""


# ---------------------------------------------------------------------------
# Patch 1a: Fast path
# ---------------------------------------------------------------------------

class TestFastPathE2E:
    """Fast path: fast_guidance_node → END."""

    @pytest.mark.asyncio
    async def test_fast_path_output_has_disclaimer(self):
        """Fast output must carry the deterministic FAST_PATH_DISCLAIMER."""
        state = _make_e2e_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist FKM?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="FKM ist ein Fluorelastomer.")
        )
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await compiled_graph.ainvoke(state)

        reply = _get_last_ai_message(result)
        assert FAST_PATH_DISCLAIMER in reply, (
            "Fast path output must end with FAST_PATH_DISCLAIMER"
        )

    @pytest.mark.asyncio
    async def test_fast_path_does_not_contain_structured_suffix(self):
        """Fast path must NOT produce the structured-path boundary suffix."""
        state = _make_e2e_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist NBR?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="NBR ist ein Nitrilkautschuk.")
        )
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await compiled_graph.ainvoke(state)

        reply = _get_last_ai_message(result)
        assert STRUCTURED_PATH_SUFFIX not in reply, (
            "Fast path must not produce the structured-path suffix"
        )

    @pytest.mark.asyncio
    async def test_fast_path_guard_fires_on_violation(self):
        """When LLM output violates policy, guard fallback is used instead."""
        state = _make_e2e_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Frage")],
        )
        # Inject a manufacturer name — the output guard must block this
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="Ich empfehle Trelleborg für diese Anwendung.")
        )
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await compiled_graph.ainvoke(state)

        reply = _get_last_ai_message(result)
        assert FAST_PATH_GUARD_FALLBACK in reply, (
            "Policy violation in fast path must trigger FAST_PATH_GUARD_FALLBACK"
        )
        assert "Trelleborg" not in reply, "Manufacturer name must not appear after guard"


# ---------------------------------------------------------------------------
# Patch 1b: Meta path
# ---------------------------------------------------------------------------

class TestMetaPathE2E:
    """Meta path: meta_response_node → END. No LLM required."""

    @pytest.mark.asyncio
    async def test_meta_path_no_asserted_state(self):
        """Empty session → all params listed as missing, with session-hint."""
        state = _make_e2e_state(
            policy_path="meta",
            messages=[HumanMessage(content="Was fehlt noch?")],
        )
        result = await compiled_graph.ainvoke(state)
        reply = _get_last_ai_message(result)

        assert "Noch keine technischen Angaben bestätigt" in reply
        assert "Betriebsdruck" in reply
        assert "Betriebstemperatur" in reply
        assert "Wellendurchmesser" in reply

    @pytest.mark.asyncio
    async def test_meta_path_with_asserted_medium(self):
        """Asserted medium shows as confirmed, not missing."""
        state = _make_e2e_state(
            policy_path="meta",
            messages=[HumanMessage(content="Was hast du bisher?")],
        )
        state["sealing_state"]["asserted"]["medium_profile"] = {"name": "Hydrauliköl"}

        result = await compiled_graph.ainvoke(state)
        reply = _get_last_ai_message(result)

        assert "Hydrauliköl" in reply
        assert "Bestätigte Angaben" in reply

    @pytest.mark.asyncio
    async def test_meta_path_does_not_show_working_profile_as_confirmed(self):
        """working_profile values must NOT appear as confirmed in meta status reply.

        Meta reads only asserted_state. Even if wp has a medium value, the
        meta response must NOT list it under "Bestätigte Angaben".
        """
        state = _make_e2e_state(
            policy_path="meta",
            messages=[HumanMessage(content="Wie ist der Stand?")],
        )
        # Use a distinctive medium that won't appear in generic example text
        state["working_profile"] = {"medium": "Kühlmittel-XR99", "pressure_bar": 5.0}
        # asserted is empty — wp values are pending only

        result = await compiled_graph.ainvoke(state)
        reply = _get_last_ai_message(result)

        # Meta reads only asserted — the wp medium must not appear at all
        assert "Kühlmittel-XR99" not in reply, (
            "working_profile medium must not appear in meta response "
            "(meta reads only asserted_state, not working_profile)"
        )
        # And no "confirmed" block should exist when asserted is empty
        assert "Bestätigte Angaben" not in reply

    @pytest.mark.asyncio
    async def test_meta_path_includes_disclaimer_note(self):
        """Meta reply must contain the 'only confirmed values' hint."""
        state = _make_e2e_state(
            policy_path="meta",
            messages=[HumanMessage(content="Was fehlt?")],
        )
        result = await compiled_graph.ainvoke(state)
        reply = _get_last_ai_message(result)

        assert "bestätigt" in reply.lower(), (
            "Meta reply must note that only confirmed session values are shown"
        )


# ---------------------------------------------------------------------------
# Patch 1c: Blocked path
# ---------------------------------------------------------------------------

class TestBlockedPathE2E:
    """Blocked path: blocked_node → END. No LLM required."""

    @pytest.mark.asyncio
    async def test_blocked_path_contains_refusal(self):
        """Blocked output must contain the deterministic refusal text."""
        state = _make_e2e_state(
            policy_path="blocked",
            messages=[HumanMessage(content="Welchen Hersteller empfiehlst du?")],
        )
        result = await compiled_graph.ainvoke(state)
        reply = _get_last_ai_message(result)

        # Core refusal content
        assert "SealAI darf weder Hersteller nennen" in reply

    @pytest.mark.asyncio
    async def test_blocked_path_does_not_answer_the_question(self):
        """Blocked reply must not contain any advisory or guidance content."""
        state = _make_e2e_state(
            policy_path="blocked",
            messages=[HumanMessage(content="Welches Material soll ich nehmen?")],
        )
        result = await compiled_graph.ainvoke(state)
        reply = _get_last_ai_message(result)

        # Must not give any substantive material guidance
        assert STRUCTURED_PATH_SUFFIX not in reply, (
            "Blocked path must not produce structured-path boundary"
        )

    @pytest.mark.asyncio
    async def test_blocked_path_redirects_to_parameters(self):
        """Blocked reply must offer the compliant path (parameter input)."""
        state = _make_e2e_state(
            policy_path="blocked",
            messages=[HumanMessage(content="Empfiehl mir eine Dichtung")],
        )
        result = await compiled_graph.ainvoke(state)
        reply = _get_last_ai_message(result)

        assert "Betriebsparameter" in reply or "Medium" in reply, (
            "Blocked reply must redirect user toward the compliant parameter-input path"
        )


# ---------------------------------------------------------------------------
# Patch 1d: Structured path
# ---------------------------------------------------------------------------

class TestStructuredPathE2E:
    """Structured path: reasoning_node → selection_node → final_response_node → END."""

    @pytest.mark.asyncio
    async def test_structured_path_output_has_scope_of_validity_suffix(self):
        """Structured output must contain STRUCTURED_PATH_SUFFIX."""
        state = _make_e2e_state(
            policy_path="structured",
            result_form="deterministic_result",
            messages=[HumanMessage(content="Welle 50mm, 3000 rpm, 8 bar, 80°C, Hydrauliköl")],
        )
        # LLM mock: no tool calls → goes directly to selection_node
        llm_mock = MagicMock()
        llm_mock.bind_tools = MagicMock(return_value=llm_mock)
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="Parameter erfasst.")
        )
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await compiled_graph.ainvoke(state)

        reply = _get_last_ai_message(result)
        assert STRUCTURED_PATH_SUFFIX in reply, (
            "Structured path output must always contain STRUCTURED_PATH_SUFFIX"
        )

    @pytest.mark.asyncio
    async def test_structured_path_does_not_use_fast_disclaimer(self):
        """Structured path must NOT produce the fast-path disclaimer text."""
        state = _make_e2e_state(
            policy_path="structured",
            messages=[HumanMessage(content="Berechne RWDR 50mm 1500 rpm")],
        )
        llm_mock = MagicMock()
        llm_mock.bind_tools = MagicMock(return_value=llm_mock)
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="Kein Hinweis.")
        )
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await compiled_graph.ainvoke(state)

        reply = _get_last_ai_message(result)
        assert FAST_PATH_DISCLAIMER not in reply, (
            "Structured path must not produce the fast-path disclaimer"
        )

    @pytest.mark.asyncio
    async def test_structured_path_with_no_evidence_includes_note(self):
        """When RAG returns nothing, the no-evidence note appears in the boundary."""
        from app.agent.agent.boundaries import _NO_EVIDENCE_NOTE

        state = _make_e2e_state(
            policy_path="structured",
            messages=[HumanMessage(content="Technische Anfrage")],
        )
        llm_mock = MagicMock()
        llm_mock.bind_tools = MagicMock(return_value=llm_mock)
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="Keine Referenzdaten.")
        )
        # RAG returns nothing → evidence_available=False
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await compiled_graph.ainvoke(state)

        reply = _get_last_ai_message(result)
        assert _NO_EVIDENCE_NOTE in reply, (
            "When RAG returns no evidence, _NO_EVIDENCE_NOTE must appear in boundary"
        )


# ---------------------------------------------------------------------------
# Phase 1B — PATCH 4: review_state / demo_data_present wired into final_response_node
# ---------------------------------------------------------------------------

class TestFinalResponseNodeCloseout:
    """Phase 1B PATCH 4: final_response_node passes full review_state + demo_data_present."""

    @pytest.mark.asyncio
    async def test_manufacturer_validation_triggers_correct_reply(self):
        """governance.release_status=manufacturer_validation_required → MANUFACTURER_VALIDATION_REPLY.

        selection_node sets review_required=True via evaluate_review_trigger().
        final_response_node routes to MANUFACTURER_VALIDATION_REPLY (governance-specific
        state takes priority in routing), confirming review_state is wired through.
        """
        from app.agent.agent.selection import MANUFACTURER_VALIDATION_REPLY
        state = _make_e2e_state(policy_path="structured")
        # Governance says manufacturer_validation_required → evaluate_review_trigger fires
        state["sealing_state"]["governance"]["release_status"] = "manufacturer_validation_required"
        state["sealing_state"]["governance"]["rfq_admissibility"] = "provisional"
        # Asserted state with core params
        state["sealing_state"]["asserted"]["medium_profile"] = {"name": "Hydrauliköl"}
        state["sealing_state"]["asserted"]["operating_conditions"] = {
            "pressure": 10.0, "temperature": 80.0,
        }
        llm_mock = MagicMock()
        llm_mock.bind_tools = MagicMock(return_value=llm_mock)
        llm_mock.ainvoke = AsyncMock(return_value=AIMessage(content="Vorläufige Beurteilung."))
        _fake_cards = [{"id": "card-test", "material_family": "NBR", "evidence_id": "card-test"}]
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=(_fake_cards, "tier1")), \
             patch("app.agent.agent.graph.REGISTRY_IS_DEMO_ONLY", False):
            result = await compiled_graph.ainvoke(state)

        reply = _get_last_ai_message(result)
        assert MANUFACTURER_VALIDATION_REPLY in reply, (
            "governance.release_status=manufacturer_validation_required must produce "
            "MANUFACTURER_VALIDATION_REPLY in the final structured-path output"
        )

    @pytest.mark.asyncio
    async def test_handover_layer_populated_on_structured_path(self):
        """After final_response_node, sealing_state.handover must be present."""
        state = _make_e2e_state(policy_path="structured")
        llm_mock = MagicMock()
        llm_mock.bind_tools = MagicMock(return_value=llm_mock)
        llm_mock.ainvoke = AsyncMock(return_value=AIMessage(content="Analyse abgeschlossen."))
        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await compiled_graph.ainvoke(state)

        handover = result["sealing_state"].get("handover")
        assert handover is not None, (
            "sealing_state.handover must be populated after final_response_node"
        )
        assert "is_handover_ready" in handover, (
            "handover dict must contain is_handover_ready key"
        )
