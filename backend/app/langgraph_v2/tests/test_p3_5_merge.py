"""Tests for P3.5 Merge Node (Sprint 5)."""

from __future__ import annotations

import pytest

from app.langgraph_v2.state import Source, WorkingMemory
from app.services.rag.nodes.p3_5_merge import node_p3_5_merge


def _make_state(**overrides):
    from app.langgraph_v2.state import SealAIState

    defaults = {
        "messages": [],
        "user_id": "test-user",
        "thread_id": "test-thread",
        "run_id": "test-run",
    }
    defaults.update(overrides)
    return SealAIState(**defaults)


class TestNodeP35Merge:
    def test_merges_p2_and_p3_results(self):
        state = _make_state()
        p2_result = {
            "sources": [
                Source(snippet="NBR 70 Shore A", source="catalog.pdf", metadata={"panel": "p2_rag_lookup"}),
            ],
            "context": "NBR 70 Shore A für Dampfanwendungen",
            "retrieval_meta": {"k_returned": 1},
            "working_memory": WorkingMemory(
                panel_material={"rag_context": "NBR context", "technical_docs": [{"text": "doc"}]}
            ),
        }
        p3_result = {
            "gap_report": {
                "missing_critical": ["flange_standard", "flange_dn"],
                "missing_optional": ["bolt_count", "bolt_size"],
                "coverage_ratio": 0.4,
                "recommendation_ready": False,
                "high_impact_gaps": ["flange_standard", "flange_dn"],
            },
        }
        result = node_p3_5_merge(state, results=[p2_result, p3_result])

        assert result["last_node"] == "node_p3_5_merge"
        # Gap report mapped to state fields
        assert result["gap_report"]["missing_critical"] == ["flange_standard", "flange_dn"]
        assert result["discovery_missing"] == ["flange_standard", "flange_dn"]
        assert result["coverage_score"] == 0.4
        assert result["recommendation_ready"] is False
        # Sources from P2 merged
        assert len(result["sources"]) == 1
        assert result["sources"][0].source == "catalog.pdf"
        # Context from P2
        assert "NBR 70" in result["context"]
        # Working memory from P2
        assert result["working_memory"].panel_material["rag_context"] == "NBR context"

    def test_handles_empty_p2(self):
        """P2 returned nothing (sparse profile), P3 has report."""
        state = _make_state()
        p2_result = {
        }
        p3_result = {
            "gap_report": {
                "missing_critical": ["medium", "pressure_max_bar", "temperature_max_c", "flange_standard", "flange_dn"],
                "missing_optional": [],
                "coverage_ratio": 0.0,
                "recommendation_ready": False,
                "high_impact_gaps": ["medium", "pressure_max_bar", "temperature_max_c", "flange_standard", "flange_dn"],
            },
        }
        result = node_p3_5_merge(state, results=[p2_result, p3_result])

        assert result["last_node"] == "node_p3_5_merge"
        assert result["recommendation_ready"] is False
        assert len(result["gap_report"]["missing_critical"]) == 5
        assert "sources" not in result or len(result.get("sources", [])) == 0

    def test_handles_no_results(self):
        state = _make_state()
        result = node_p3_5_merge(state, results=[])

        assert result["last_node"] == "node_p3_5_merge"
        assert "gap_report" not in result or result.get("gap_report") == {}

    def test_deduplicates_sources(self):
        existing_source = Source(snippet="existing", source="a.pdf", metadata={})
        state = _make_state(sources=[existing_source])
        p2_result = {
            "sources": [
                Source(snippet="existing", source="a.pdf", metadata={}),  # duplicate
                Source(snippet="new", source="b.pdf", metadata={}),
            ],
        }
        result = node_p3_5_merge(state, results=[p2_result, {}])

        assert len(result["sources"]) == 2  # 1 existing + 1 new (duplicate removed)
