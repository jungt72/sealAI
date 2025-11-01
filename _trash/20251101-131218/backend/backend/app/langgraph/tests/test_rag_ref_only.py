# MIGRATION: Phase-2 – RAG references only test
"""Test that RAG retrieval stores only references in context_refs, no full content."""
from __future__ import annotations

import pytest

from app.langgraph.state import ContextRef, SealAIStateModel
from app.langgraph.subgraphs.material.nodes.rag_select import MaterialRAGSelectNode


@pytest.fixture
def material_rag_node():
    return MaterialRAGSelectNode()


@pytest.fixture
def sample_state():
    return {
        "messages": [
            {
                "role": "user",
                "content": "What material for high pressure seals?",
                "name": None,
                "tool_call_id": None,
                "meta": {}
            }
        ],
        "slots": {},
        "routing": {"domains": ["material"], "primary_domain": "material"},
        "context_refs": [],
        "meta": {"thread_id": "test-123", "user_id": "user-456", "trace_id": "trace-789"}
    }


def test_rag_select_stores_only_references(material_rag_node, sample_state):
    """Test that RAG select stores only ContextRef objects, no full content."""
    result = material_rag_node(sample_state)

    # Validate state
    model = SealAIStateModel.model_validate(result)

    # Check that context_refs contains only ContextRef objects
    for ref in model.context_refs:
        assert isinstance(ref, ContextRef)
        assert ref.kind == "rag"
        assert isinstance(ref.id, str)
        assert len(ref.id) > 0

        # Check meta structure
        assert "score" in ref.meta
        assert "source" in ref.meta
        assert isinstance(ref.meta["score"], (int, float))
        assert isinstance(ref.meta["source"], str)


def test_rag_cache_integration(material_rag_node, sample_state):
    """Test that RAG caching works and returns same results for same query."""
    # First call
    result1 = material_rag_node(sample_state)
    refs1 = result1["context_refs"]

    # Second call with same query should use cache
    result2 = material_rag_node(sample_state)
    refs2 = result2["context_refs"]

    # Should have same number of references
    assert len(refs1) == len(refs2)

    # References should be structurally equivalent
    for ref1, ref2 in zip(refs1, refs2):
        assert ref1["kind"] == ref2["kind"]
        assert ref1["id"] == ref2["id"]
        assert ref1["meta"]["score"] == ref2["meta"]["score"]


def test_rag_filters_integration(material_rag_node, sample_state):
    """Test that domain filters are applied correctly."""
    # Add domain filters to slots
    sample_state["slots"]["domain_filters"] = {"temperature_range": "high"}

    result = material_rag_node(sample_state)

    # Should still work and return references
    model = SealAIStateModel.model_validate(result)
    assert isinstance(model.context_refs, list)


__all__ = []