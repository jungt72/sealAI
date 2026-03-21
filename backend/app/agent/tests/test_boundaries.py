"""
Unit tests for Phase 0B.1 (Registry Quarantine) and Phase 0B.2 (Boundary Communication).

Tests cover:
1. Registry: is_demo_only flag on PromotedCandidateRegistryRecordDTO
2. Registry: REGISTRY_IS_DEMO_ONLY module constant
3. Registry: demo_data_in_scope in MaterialQualificationCoreOutput
4. Boundary: build_boundary_block — fast path always returns orientation disclaimer
5. Boundary: build_boundary_block — structured path with coverage / known_unknowns / demo flag
6. Integration: build_final_reply appends boundary block deterministically
7. Integration: fast_guidance_node appends disclaimer to LLM content (async)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.agent.boundaries import (
    FAST_PATH_DISCLAIMER,
    STRUCTURED_PATH_SUFFIX,
    _DEMO_DATA_NOTE,
    _COVERAGE_NOTES,
    build_boundary_block,
)
from app.agent.agent.selection import build_final_reply
from app.agent.material_core import (
    REGISTRY_IS_DEMO_ONLY,
    PromotedCandidateRegistryRecordDTO,
    load_promoted_candidate_registry_records,
    evaluate_material_qualification_core,
)
from app.agent.tests.test_graph_routing import _make_state


# ---------------------------------------------------------------------------
# 0B.1 — Registry quarantine
# ---------------------------------------------------------------------------

class TestRegistryQuarantine:
    def test_registry_is_demo_only_constant_is_true(self):
        """Module-level flag: current registry is demo-only until governed data is wired."""
        assert REGISTRY_IS_DEMO_ONLY is True

    def test_default_record_is_demo_only(self):
        record = PromotedCandidateRegistryRecordDTO(
            registry_record_id="test-record",
            material_family="PTFE",
        )
        assert record.is_demo_only is True

    def test_governed_record_is_not_demo_only(self):
        record = PromotedCandidateRegistryRecordDTO(
            registry_record_id="governed-record",
            material_family="FKM",
            registry_authority="governed",
        )
        assert record.is_demo_only is False

    def test_all_loaded_records_are_demo_only(self):
        """All current registry entries must carry demo_only authority."""
        records = load_promoted_candidate_registry_records()
        assert len(records) > 0, "registry must not be empty"
        for record in records:
            assert record.is_demo_only, (
                f"Record {record.registry_record_id!r} has registry_authority="
                f"{record.registry_authority!r} — expected demo_only"
            )

    def test_invalid_registry_authority_raises(self):
        with pytest.raises(ValueError, match="registry_authority must be"):
            PromotedCandidateRegistryRecordDTO(
                registry_record_id="bad",
                material_family="NBR",
                registry_authority="unverified",  # not a valid value
            )

    def test_evaluate_material_qualification_core_sets_demo_data_in_scope(self):
        """demo_data_in_scope must be True whenever REGISTRY_IS_DEMO_ONLY."""
        result = evaluate_material_qualification_core(
            relevant_fact_cards=[],
            asserted_state={},
            governance_state={},
        )
        assert result.demo_data_in_scope is True

    def test_evaluate_material_qualification_core_with_demo_record_in_assessments(self):
        """demo_data_in_scope is True when at least one assessment has a demo record."""
        card = {
            "id": "ev-001",
            "evidence_id": "ev-001",
            "source_ref": "test-ref",
            "metadata": {
                "material_family": "PTFE",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
            },
        }
        result = evaluate_material_qualification_core(
            relevant_fact_cards=[card],
            asserted_state={},
            governance_state={},
        )
        assert result.demo_data_in_scope is True


# ---------------------------------------------------------------------------
# 0B.2 — build_boundary_block
# ---------------------------------------------------------------------------

class TestBuildBoundaryBlock:
    def test_fast_path_returns_orientation_disclaimer(self):
        block = build_boundary_block("fast")
        assert block == FAST_PATH_DISCLAIMER

    def test_fast_path_ignores_coverage_status(self):
        """Fast path always returns the same disclaimer regardless of coverage_status."""
        for status in ("full", "partial", "limited", None):
            assert build_boundary_block("fast", coverage_status=status) == FAST_PATH_DISCLAIMER

    def test_fast_path_ignores_known_unknowns(self):
        block = build_boundary_block("fast", known_unknowns=["medium", "pressure"])
        assert block == FAST_PATH_DISCLAIMER

    def test_structured_path_always_contains_suffix(self):
        block = build_boundary_block("structured")
        assert STRUCTURED_PATH_SUFFIX in block

    def test_structured_path_starts_with_separator(self):
        block = build_boundary_block("structured")
        assert block.startswith("---")

    def test_structured_path_coverage_full(self):
        block = build_boundary_block("structured", coverage_status="full")
        assert _COVERAGE_NOTES["full"] in block

    def test_structured_path_coverage_partial(self):
        block = build_boundary_block("structured", coverage_status="partial")
        assert _COVERAGE_NOTES["partial"] in block

    def test_structured_path_coverage_limited(self):
        block = build_boundary_block("structured", coverage_status="limited")
        assert _COVERAGE_NOTES["limited"] in block

    def test_structured_path_unknown_coverage_status_omitted(self):
        """Unknown coverage_status must not cause an error; just omit the coverage note."""
        block = build_boundary_block("structured", coverage_status="unknown_future_value")
        assert STRUCTURED_PATH_SUFFIX in block  # at minimum, the suffix is there

    def test_structured_path_known_unknowns_listed(self):
        block = build_boundary_block(
            "structured",
            known_unknowns=["medium", "pressure", "temperature"],
        )
        assert "medium" in block
        assert "pressure" in block
        assert "temperature" in block

    def test_structured_path_empty_known_unknowns_omitted(self):
        block_with = build_boundary_block("structured", known_unknowns=["medium"])
        block_without = build_boundary_block("structured", known_unknowns=[])
        assert "medium" in block_with
        assert "medium" not in block_without

    def test_structured_path_demo_data_note_present_when_flagged(self):
        block = build_boundary_block("structured", demo_data_present=True)
        assert _DEMO_DATA_NOTE in block

    def test_structured_path_demo_data_note_absent_when_not_flagged(self):
        block = build_boundary_block("structured", demo_data_present=False)
        assert _DEMO_DATA_NOTE not in block


# ---------------------------------------------------------------------------
# Integration: build_final_reply always appends boundary
# ---------------------------------------------------------------------------

def _make_minimal_selection_state(*, selection_status: str = "blocked_no_candidates") -> dict:
    return {
        "selection_status": selection_status,
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "output_blocked": True,
        "candidates": [],
        "viable_candidate_ids": [],
        "blocked_candidates": [],
        "winner_candidate_id": None,
        "recommendation_artifact": {
            "selection_status": selection_status,
            "winner_candidate_id": None,
            "candidate_ids": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "evidence_basis": [],
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
            "trace_provenance_refs": [],
        },
    }


class TestBuildFinalReplyBoundary:
    def test_boundary_separator_always_present(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(state)
        assert "---" in reply

    def test_structured_suffix_always_present(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(state)
        assert STRUCTURED_PATH_SUFFIX in reply

    def test_core_reply_precedes_boundary(self):
        """Core governance text appears before the boundary separator."""
        state = _make_minimal_selection_state(selection_status="blocked_no_candidates")
        reply = build_final_reply(state)
        sep_pos = reply.index("---")
        core_pos = reply.index("No governed")
        assert core_pos < sep_pos

    def test_known_unknowns_forwarded(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(state, known_unknowns=["medium", "temperature"])
        assert "medium" in reply
        assert "temperature" in reply

    def test_demo_data_note_forwarded(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(state, demo_data_present=True)
        assert _DEMO_DATA_NOTE in reply

    def test_no_demo_note_by_default(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(state)
        assert _DEMO_DATA_NOTE not in reply

    def test_all_governance_branches_have_boundary(self):
        """Every code path in build_final_reply must produce a boundary block."""
        from app.agent.agent.selection import (
            SAFEGUARDED_WITHHELD_REPLY,
            NO_CANDIDATES_REPLY,
            MISSING_INPUTS_REPLY,
            NO_VIABLE_CANDIDATES_REPLY,
        )
        # Test misaligned artifact path (SAFEGUARDED)
        state_misaligned = {**_make_minimal_selection_state(), "recommendation_artifact": {}}
        reply_misaligned = build_final_reply(state_misaligned)
        assert SAFEGUARDED_WITHHELD_REPLY in reply_misaligned
        assert STRUCTURED_PATH_SUFFIX in reply_misaligned

        # Test blocked_missing_required_inputs path
        state_missing = _make_minimal_selection_state(selection_status="blocked_missing_required_inputs")
        reply_missing = build_final_reply(state_missing)
        assert MISSING_INPUTS_REPLY in reply_missing
        assert STRUCTURED_PATH_SUFFIX in reply_missing

        # Test blocked_no_viable_candidates path
        state_nv = _make_minimal_selection_state(selection_status="blocked_no_viable_candidates")
        reply_nv = build_final_reply(state_nv)
        assert NO_VIABLE_CANDIDATES_REPLY in reply_nv
        assert STRUCTURED_PATH_SUFFIX in reply_nv


# ---------------------------------------------------------------------------
# Integration: fast_guidance_node appends disclaimer to LLM content
# ---------------------------------------------------------------------------

class TestFastGuidanceNodeBoundary:
    @pytest.mark.asyncio
    async def test_fast_guidance_node_appends_disclaimer(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from app.agent.agent.graph import fast_guidance_node

        state = _make_state(
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
            result = await fast_guidance_node(state)

        content = result["messages"][0].content
        assert FAST_PATH_DISCLAIMER in content, (
            "Fast-path disclaimer must be appended deterministically to LLM output"
        )

    @pytest.mark.asyncio
    async def test_fast_guidance_node_llm_content_precedes_disclaimer(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from app.agent.agent.graph import fast_guidance_node

        llm_text = "FKM ist ein Fluorelastomer mit hoher Chemikalienbeständigkeit."
        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist FKM?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(return_value=AIMessage(content=llm_text))

        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        content = result["messages"][0].content
        llm_pos = content.index(llm_text)
        disclaimer_pos = content.index("---")
        assert llm_pos < disclaimer_pos, "LLM text must come before the boundary separator"

    @pytest.mark.asyncio
    async def test_fast_guidance_node_disclaimer_is_not_llm_generated(self):
        """LLM returns empty string — disclaimer still appears (deterministic injection)."""
        from langchain_core.messages import AIMessage, HumanMessage
        from app.agent.agent.graph import fast_guidance_node

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(return_value=AIMessage(content=""))

        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        content = result["messages"][0].content
        assert FAST_PATH_DISCLAIMER in content
