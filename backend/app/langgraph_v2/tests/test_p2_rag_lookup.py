"""Tests for P2 RAG Material-Lookup Node (Sprint 5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.rag.nodes.p2_rag_lookup import (
    _build_rag_query,
    node_p2_rag_lookup,
)
from app.services.rag.state import WorkingProfile


def _make_state(**overrides):
    """Build a minimal SealAIState-like object for testing."""
    from app.langgraph_v2.state import SealAIState

    defaults = {
        "messages": [],
        "user_id": "test-user",
        "thread_id": "test-thread",
        "run_id": "test-run",
    }
    defaults.update(overrides)
    return SealAIState(**defaults)


class TestBuildRagQuery:
    def test_empty_profile(self):
        profile = WorkingProfile()
        query = _build_rag_query(profile)
        assert query == "Dichtungswerkstoff"

    def test_full_profile(self):
        profile = WorkingProfile(
            medium="Dampf",
            medium_detail="gesättigter Dampf",
            pressure_max_bar=150.0,
            temperature_max_c=400.0,
            flange_standard="EN 1092-1",
            flange_dn=100,
            flange_pn=40,
            emission_class="TA-Luft",
            industry_sector="Petrochemie",
        )
        query = _build_rag_query(profile)
        assert "Dampf" in query
        assert "gesättigter Dampf" in query
        assert "150.0 bar" in query
        assert "400.0°C" in query
        assert "EN 1092-1 DN100 PN40" in query
        assert "TA-Luft" in query
        assert "Petrochemie" in query

    def test_partial_profile_pressure_only(self):
        profile = WorkingProfile(pressure_max_bar=50.0)
        query = _build_rag_query(profile)
        assert "50.0 bar" in query
        assert "°C" not in query


class TestNodeP2RagLookup:
    def test_sparse_profile_skips_rag(self):
        """Coverage < 0.2 → skip RAG, return minimal state."""
        state = _make_state(working_profile=WorkingProfile())
        result = node_p2_rag_lookup(state)
        assert "context" not in result  # no RAG context
        assert "sources" not in result

    def test_no_profile_skips_rag(self):
        state = _make_state(working_profile=None)
        result = node_p2_rag_lookup(state)
        assert "context" not in result

    @patch("app.services.rag.nodes.p2_rag_lookup.search_technical_docs")
    def test_filled_profile_calls_rag(self, mock_search):
        mock_search.return_value = {
            "hits": [
                {
                    "text": "NBR 70 Shore A — geeignet für Dampf bis 180°C",
                    "source": "material_catalog.pdf",
                    "vector_score": 0.85,
                    "metadata": {"page": 12},
                }
            ],
            "context": "NBR 70 Shore A für Dampfanwendungen",
            "retrieval_meta": {"k_returned": 1, "top_scores": [0.85]},
        }
        profile = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=10.0,
            temperature_max_c=180.0,
            flange_standard="EN 1092-1",
            flange_dn=50,
        )
        state = _make_state(working_profile=profile)
        result = node_p2_rag_lookup(state)

        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs.kwargs.get("tenant_id") == "test-user" or call_kwargs[1].get("tenant_id") == "test-user"

        assert len(result["sources"]) == 1
        assert result["sources"][0].source == "material_catalog.pdf"
        assert "NBR 70" in result["context"]
        assert result["working_memory"].panel_material["source"] == "p2_rag_lookup"

    @patch("app.services.rag.nodes.p2_rag_lookup.search_technical_docs")
    def test_rag_failure_graceful(self, mock_search):
        mock_search.side_effect = RuntimeError("Qdrant timeout")
        profile = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=10.0,
            temperature_max_c=180.0,
            flange_standard="EN 1092-1",
            flange_dn=50,
        )
        state = _make_state(working_profile=profile)
        result = node_p2_rag_lookup(state)

        assert "error" in str(result.get("retrieval_meta", {})).lower() or "RuntimeError" in str(result.get("retrieval_meta", {}))
