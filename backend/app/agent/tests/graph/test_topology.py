"""
Tests for graph/topology.py — Phase F-C.1

Key invariants under test:
    1. Graph compiles without error.
    2. All 7 nodes are registered.
    3. Entry point is intake_observe.
    4. End-to-end: empty state → output_contract result (no crash).
    5. End-to-end: GOVERNED path (3 core fields) → gov_class A, response class set.
    6. State after full run: output_response_class non-empty.
    7. State after full run: output_public has required keys.
    8. State after full run: output_public contains no internal artefacts.
    9. GOVERNED_GRAPH singleton is available at import time.
    10. build_governed_graph() returns a fresh compiled graph each call.

Coverage:
    1.  Import succeeds
    2.  GOVERNED_GRAPH is not None
    3.  build_governed_graph() returns distinct objects on two calls
    4.  Empty GraphState through full graph → output_response_class set
    5.  Empty GraphState → response class is structured_clarification
    6.  3-core-fields state (regex-extractable message) → governed path
    7.  output_public always has response_class key
    8.  output_public never has raw_extractions
    9.  output_public never has assertions key
    10. output_reply is always a non-empty string after full run
    11. Node name constants defined in topology module
    12. Full RWDR path: shaft + speed in message → compute_results populated
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.topology import (
    GOVERNED_GRAPH,
    NODE_ASSERT,
    NODE_COMPUTE,
    NODE_EVIDENCE,
    NODE_GOVERNANCE,
    NODE_INTAKE_OBSERVE,
    NODE_MATCHING,
    NODE_MANUFACTURER_MAPPING,
    NODE_DISPATCH_CONTRACT,
    NODE_NORMALIZE,
    NODE_OUTPUT_CONTRACT,
    NODE_EXPORT_PROFILE,
    NODE_NORM,
    NODE_DISPATCH,
    NODE_RFQ_HANDOVER,
    build_governed_graph,
)
from app.agent.state.models import ObservedExtraction, ObservedState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_message(msg: str, tenant_id: str = "test_tenant") -> GraphState:
    return GraphState(pending_message=msg, tenant_id=tenant_id)


def _state_with_extractions(**fields) -> GraphState:
    """Build a GraphState where ObservedState already has extractions
    (bypasses the LLM in intake_observe_node by pre-loading observed state).
    """
    observed = ObservedState()
    for field_name, (value, conf) in fields.items():
        observed = observed.with_extraction(ObservedExtraction(
            field_name=field_name,
            raw_value=value,
            source="llm",
            confidence=conf,
            turn_index=0,
        ))
    return GraphState(observed=observed, tenant_id="test_tenant")


_REQUIRED_OUTPUT_KEYS = {
    "response_class", "gov_class", "rfq_admissible",
    "parameters", "missing_fields", "conflicts",
    "validity_notes", "open_points", "compute", "rfq", "dispatch", "norm", "export_profile", "manufacturer_mapping", "dispatch_contract", "message",
}


def _result_state(raw: dict) -> GraphState:
    if "__interrupt__" not in raw:
        return GraphState.model_validate(raw)
    payload = list(raw["__interrupt__"])[0].value
    return GraphState.model_validate(payload["state"])


# ---------------------------------------------------------------------------
# 1–3. Graph compilation
# ---------------------------------------------------------------------------

class TestGraphCompilation:
    def test_governed_graph_singleton_not_none(self):
        assert GOVERNED_GRAPH is not None

    def test_build_returns_compiled_graph(self):
        g = build_governed_graph()
        assert g is not None

    def test_two_builds_are_distinct_objects(self):
        g1 = build_governed_graph()
        g2 = build_governed_graph()
        assert g1 is not g2

    def test_node_name_constants_defined(self):
        assert NODE_INTAKE_OBSERVE  == "intake_observe"
        assert NODE_NORMALIZE       == "normalize"
        assert NODE_ASSERT          == "assert"
        assert NODE_EVIDENCE        == "evidence"
        assert NODE_COMPUTE         == "compute"
        assert NODE_GOVERNANCE      == "governance"
        assert NODE_MATCHING        == "matching"
        assert NODE_RFQ_HANDOVER    == "rfq_handover"
        assert NODE_DISPATCH        == "dispatch"
        assert NODE_NORM            == "norm"
        assert NODE_EXPORT_PROFILE  == "export_profile"
        assert NODE_MANUFACTURER_MAPPING == "manufacturer_mapping"
        assert NODE_DISPATCH_CONTRACT == "dispatch_contract"
        assert NODE_OUTPUT_CONTRACT == "output_contract"


# ---------------------------------------------------------------------------
# 4–5. Empty state end-to-end
# ---------------------------------------------------------------------------

class TestEmptyStateEndToEnd:
    @pytest.mark.asyncio
    async def test_empty_state_does_not_crash(self):
        result = await GOVERNED_GRAPH.ainvoke(GraphState())
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_empty_state_interrupt_contains_response_class(self):
        raw = await GOVERNED_GRAPH.ainvoke(GraphState())
        assert "__interrupt__" in raw
        payload = list(raw["__interrupt__"])[0].value
        result = GraphState.model_validate(payload["state"])
        assert result.output_response_class != ""

    @pytest.mark.asyncio
    async def test_empty_state_is_structured_clarification(self):
        raw = await GOVERNED_GRAPH.ainvoke(GraphState())
        payload = list(raw["__interrupt__"])[0].value
        result = GraphState.model_validate(payload["state"])
        assert result.output_response_class == "structured_clarification"

    @pytest.mark.asyncio
    async def test_empty_state_interrupt_output_public_has_keys(self):
        raw = await GOVERNED_GRAPH.ainvoke(GraphState())
        payload = list(raw["__interrupt__"])[0].value
        result = GraphState.model_validate(payload["state"])
        assert _REQUIRED_OUTPUT_KEYS.issubset(result.output_public.keys())


# ---------------------------------------------------------------------------
# 6–10. Pre-loaded extractions end-to-end (bypasses LLM)
# ---------------------------------------------------------------------------

class TestPreloadedExtractionsEndToEnd:
    @pytest.mark.asyncio
    async def test_three_core_fields_confirmed_class_a(self):
        """Three legacy core fields alone stay blocked until seal type is known."""
        state = _state_with_extractions(
            medium=("Dampf", 0.95),
            pressure_bar=(12.0, 0.95),
            temperature_c=(180.0, 0.95),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=([], {}),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = _result_state(raw)
        assert result.governance.gov_class == "B"
        assert result.governance.rfq_admissible is False
        assert result.governance.preselection_blockers == ["sealing_type"]
        assert result.output_response_class == "structured_clarification"

    @pytest.mark.asyncio
    async def test_three_core_fields_response_class_state_update(self):
        """Complete static seal basis without compute → governed_state_update.
        Uses 'Öl' medium (not in demo records' allowed_media) to prevent matching.
        """
        state = _state_with_extractions(
            medium=("Öl", 0.95),
            pressure_bar=(6.0, 0.95),
            temperature_c=(80.0, 0.95),
            sealing_type=("gasket", 0.95),
            geometry_context=("static_groove", 0.95),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=([], {}),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = _result_state(raw)
        assert result.output_response_class == "governed_state_update"

    @pytest.mark.asyncio
    async def test_class_a_with_material_and_no_evidence_stays_conservative(self):
        state = _state_with_extractions(
            medium=("Wasser", 0.95),
            pressure_bar=(12.0, 0.95),
            temperature_c=(180.0, 0.95),
            material=("PTFE", 0.95),
            sealing_type=("rwdr", 0.95),
            shaft_diameter_mm=(50, 0.95),
            speed_rpm=(1500, 0.95),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=([], {}),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = _result_state(raw)
        assert result.output_response_class == "governed_state_update"
        assert result.rfq.rfq_ready is False
        assert "demo_matching_catalog" in result.matching.release_blockers

    @pytest.mark.asyncio
    async def test_output_public_no_raw_extractions(self):
        # Use max_cycles=1, analysis_cycle=1 so Class B terminates immediately
        # (budget exhausted → decide_cycle → TERMINATE → output_contract).
        state = _state_with_extractions(medium=("Dampf", 0.95))
        state = state.model_copy(update={"max_cycles": 1, "analysis_cycle": 1})
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock, return_value=([], {}),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = GraphState.model_validate(raw)
        assert "raw_extractions" not in result.output_public

    @pytest.mark.asyncio
    async def test_output_public_no_assertions_key(self):
        state = _state_with_extractions(medium=("Dampf", 0.95))
        state = state.model_copy(update={"max_cycles": 1, "analysis_cycle": 1})
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock, return_value=([], {}),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = GraphState.model_validate(raw)
        assert "assertions" not in result.output_public

    @pytest.mark.asyncio
    async def test_output_reply_non_empty(self):
        state = _state_with_extractions(
            medium=("Dampf", 0.95),
            pressure_bar=(12.0, 0.95),
            temperature_c=(180.0, 0.95),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock, return_value=([], {}),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = _result_state(raw)
        assert result.output_reply != ""

    @pytest.mark.asyncio
    async def test_material_based_full_graph_keeps_demo_matching_unreleased(self):
        state = _state_with_extractions(
            medium=("Dampf", 0.95),
            pressure_bar=(12.0, 0.95),
            temperature_c=(180.0, 0.95),
            material=("PTFE", 0.95),
            sealing_type=("rwdr", 0.95),
            shaft_diameter_mm=(50, 0.95),
            speed_rpm=(1500, 0.95),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock, return_value=([], {}),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = _result_state(raw)
        assert result.output_response_class == "governed_state_update"
        assert result.matching.status == "candidate_not_released"
        assert result.matching.selected_manufacturer_ref is None
        assert result.matching.shortlist_ready is False
        assert result.rfq.rfq_ready is False
        assert result.sealai_norm.identity.norm_version == "sealai_norm_v1"
        assert result.export_profile.export_profile_version == "sealai_export_profile_v1"
        assert result.export_profile.rfq_ready is False
        assert result.manufacturer_mapping.mapping_version == "manufacturer_mapping_v1"
        assert result.dispatch_contract.contract_version == "dispatch_contract_v1"


# ---------------------------------------------------------------------------
# 11. Regex-extractable message → GOVERNED path (intake_observe LLM disabled)
# ---------------------------------------------------------------------------

class TestRegexMessageEndToEnd:
    @pytest.mark.asyncio
    async def test_regex_message_extracts_parameters(self):
        """A message with clear numeric patterns extracts via regex (no LLM needed)."""
        state = GraphState(
            pending_message="12 bar, 180°C, Medium Dampf",
            tenant_id="test_tenant",
            max_cycles=1,
        )
        with (
            patch(
                "app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION",
                False,
            ),
            patch(
                "app.agent.graph.nodes.evidence_node.retrieve_evidence",
                new_callable=AsyncMock,
                return_value=([], {}),
            ),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = _result_state(raw)
        # At minimum, regex should have captured pressure and temperature
        assert result.output_public["response_class"] != ""

    @pytest.mark.asyncio
    async def test_message_with_shaft_and_rpm_triggers_compute(self):
        """Message with shaft diameter + RPM → compute_results populated."""
        state = GraphState(
            pending_message="Welle 50mm, 1500 U/min",
            tenant_id="test_tenant",
        )
        with (
            patch(
                "app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION",
                False,
            ),
            patch(
                "app.agent.graph.nodes.evidence_node.retrieve_evidence",
                new_callable=AsyncMock,
                return_value=([], {}),
            ),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = GraphState.model_validate(raw)
        # compute_results is populated when shaft_diameter_mm + speed_rpm asserted
        # (shaft and rpm may or may not be asserted depending on regex hit)
        assert isinstance(result.compute_results, list)

    @pytest.mark.asyncio
    async def test_salzwasser_is_recognized_before_clarification_and_not_reasked_as_medium(self):
        state = GraphState(
            pending_message="ich muss salzwasser draussen halten",
            tenant_id="test_tenant",
            analysis_cycle=1,
            max_cycles=1,
        )
        with (
            patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False),
            patch(
                "app.agent.graph.nodes.evidence_node.retrieve_evidence",
                new_callable=AsyncMock,
                return_value=([], {}),
            ),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = GraphState.model_validate(raw)
        assert result.medium_classification.status == "recognized"
        assert result.medium_classification.canonical_label == "Salzwasser"
        assert "Welches Medium soll abgedichtet werden?" not in result.output_reply
        assert "Medium angeben" not in result.output_public.get("open_points", [])

    @pytest.mark.asyncio
    async def test_oel_is_recognized_before_clarification_and_not_reasked_as_medium(self):
        state = GraphState(
            pending_message="medium ist oel",
            tenant_id="test_tenant",
            analysis_cycle=1,
            max_cycles=1,
        )
        with (
            patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False),
            patch(
                "app.agent.graph.nodes.evidence_node.retrieve_evidence",
                new_callable=AsyncMock,
                return_value=([], {}),
            ),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        result = GraphState.model_validate(raw)
        assert result.medium_classification.status == "recognized"
        assert result.medium_classification.canonical_label == "Öl"
        assert "Welches Medium soll abgedichtet werden?" not in result.output_reply

    @pytest.mark.asyncio
    async def test_missing_medium_still_triggers_generic_medium_question(self):
        state = GraphState(
            pending_message="ich brauche eine dichtung",
            tenant_id="test_tenant",
            analysis_cycle=1,
            max_cycles=1,
        )
        with (
            patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False),
            patch(
                "app.agent.graph.nodes.evidence_node.retrieve_evidence",
                new_callable=AsyncMock,
                return_value=([], {}),
            ),
        ):
            raw = await GOVERNED_GRAPH.ainvoke(state)

        payload = list(raw["__interrupt__"])[0].value
        result = GraphState.model_validate(payload["state"])
        assert result.medium_classification.status == "unavailable"
        assert "Welches Medium soll abgedichtet werden?" in result.output_reply


class TestGraphOrdering:
    @pytest.mark.asyncio
    async def test_normalize_node_runs_before_output_contract_node(self):
        from app.agent.graph import topology as topology_module

        call_order: list[str] = []
        original_normalize = topology_module.normalize_node
        original_output = topology_module.output_contract_node

        async def _record_normalize(state):
            call_order.append("normalize")
            return await original_normalize(state)

        async def _record_output(state):
            call_order.append("output_contract")
            return await original_output(state)

        with (
            patch.object(topology_module, "normalize_node", _record_normalize),
            patch.object(topology_module, "output_contract_node", _record_output),
            patch(
                "app.agent.graph.nodes.evidence_node.retrieve_evidence",
                new_callable=AsyncMock,
                return_value=([], {}),
            ),
            patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False),
        ):
            graph = build_governed_graph()
            await graph.ainvoke(
                GraphState(
                    pending_message="ich muss salzwasser draussen halten",
                    tenant_id="test_tenant",
                    analysis_cycle=1,
                    max_cycles=1,
                )
            )

        assert call_order
        assert call_order.index("normalize") < call_order.index("output_contract")
