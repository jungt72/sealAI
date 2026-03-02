from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

pytest.importorskip("prometheus_client")

import app.services.rag.nodes.p2_rag_lookup as rag_node
from app.langgraph_v2.state.sealai_state import SealAIState
from app.services.rag.state import WorkingProfile


class _NoCache:
    def get(self, tenant: str, query: str):  # noqa: ARG002
        return None

    def set(self, tenant: str, query: str, payload, ttl: int = 3600):  # noqa: ARG002
        return None


@pytest.mark.asyncio
async def test_force_retrieval_for_material_research_intent(monkeypatch):
    search_calls = []

    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        search_calls.append({"query": query, "tenant_id": tenant_id, "k": k})
        return {
            "hits": [{"source": "typ-iv.pdf", "document_id": "doc-typ-iv", "score": 0.81, "snippet": "TYP IV"}],
            "context": "TYP IV context",
            "retrieval_meta": {"collection": "technical_docs", "k_returned": 1, "top_scores": [0.81]},
        }

    monkeypatch.setattr(rag_node, "search_technical_docs", _fake_search_technical_docs)
    monkeypatch.setattr(rag_node, "rag_cache", _NoCache())

    state = SealAIState(
        user_id="tenant-user",
        flags={"frontdoor_intent_category": "MATERIAL_RESEARCH"},
        working_profile=WorkingProfile(),
        messages=[HumanMessage(content="Ich benötige eine Dichtungslösung.")],
    )

    patch = await rag_node.node_p2_rag_lookup(state)
    assert search_calls
    assert patch.get("context") == "TYP IV context"


@pytest.mark.asyncio
async def test_wide_search_k_for_german_technical_terms(monkeypatch):
    search_calls = []

    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        search_calls.append({"query": query, "tenant_id": tenant_id, "k": k})
        return {
            "hits": [{"source": "prelonring.pdf", "document_id": "doc-prelonring", "score": 0.77, "snippet": "Prelonring"}],
            "context": "Prelonring context",
            "retrieval_meta": {"collection": "technical_docs", "k_returned": 1, "top_scores": [0.77]},
        }

    monkeypatch.setattr(rag_node, "search_technical_docs", _fake_search_technical_docs)
    monkeypatch.setattr(rag_node, "rag_cache", _NoCache())

    state = SealAIState(
        user_id="tenant-user",
        working_profile=None,
        messages=[HumanMessage(content="Ich benötige eine Dichtungslösung für mein Rührwerk.")],
    )

    patch = await rag_node.node_p2_rag_lookup(state)
    assert search_calls
    assert search_calls[0]["k"] >= 8
    assert "Rührwerk" in search_calls[0]["query"]
    assert patch.get("context") == "Prelonring context"
