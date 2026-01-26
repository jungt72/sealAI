from app.langgraph_v2.nodes.nodes_flows import rag_support_node
from app.langgraph_v2.nodes.response_node import _normalize_sources, _sources_fallback_text, response_node
from app.langgraph_v2.state import Intent, SealAIState, Source


def test_normalize_sources_dedup_and_cap(monkeypatch):
    monkeypatch.setenv("MAX_SOURCES", "2")
    sources = [
        Source(source="https://example.com/a", metadata={"url": "https://example.com/a", "title": "A"}),
        Source(source="https://example.com/a", metadata={"url": "https://example.com/a", "title": "A"}),
        Source(source="https://example.com/b", metadata={"url": "https://example.com/b", "title": "B"}),
        Source(source="https://example.com/c", metadata={"url": "https://example.com/c", "title": "C"}),
    ]
    normalized = _normalize_sources(sources)
    assert len(normalized) == 2
    assert normalized[0].metadata.get("title") == "A"
    assert normalized[1].metadata.get("title") == "B"


def test_sources_enforced_when_needed_and_missing():
    state = SealAIState(
        needs_sources=True,
        sources=[],
    )
    patch = response_node(state)
    assert _sources_fallback_text() in patch["final_text"]
    assert patch.get("sources") == []


def test_sources_included_when_ok():
    src = Source(source="https://example.com/a", metadata={"url": "https://example.com/a", "title": "A"})
    state = SealAIState(
        needs_sources=True,
        sources=[src],
    )
    patch = response_node(state)
    assert _sources_fallback_text() not in patch["final_text"]
    assert patch.get("sources") == [src]


def test_rag_support_node_sets_sources_status(monkeypatch):
    class _StubTool:
        @staticmethod
        def invoke(_payload):
            return {
                "context": "",
                "retrieval_meta": {"skipped": True, "k_returned": 0, "top_scores": []},
            }

    monkeypatch.setattr(
        "app.langgraph_v2.nodes.nodes_flows.search_knowledge_base",
        _StubTool(),
    )

    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        tenant_id="tenant-1",
    )
    patch = rag_support_node(state)
    assert patch.get("sources_status") == "missing"
