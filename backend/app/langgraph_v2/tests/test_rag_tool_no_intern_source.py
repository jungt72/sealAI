from app.langgraph_v2.utils import rag_tool


def test_format_hit_does_not_emit_intern_source_when_missing_metadata() -> None:
    rendered = rag_tool._format_hit({"metadata": {}, "text": "x", "vector_score": 0.1})
    assert "Quelle:" not in rendered
    assert "intern" not in rendered


def test_search_knowledge_base_applies_tenant_filter(monkeypatch) -> None:
    captured = {}

    def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", fake_retrieve)
    _ = rag_tool.search_knowledge_base.invoke(
        {
            "query": "test",
            "category": "norms",
            "k": 3,
            "tenant": "tenant-1",
        }
    )
    assert captured.get("metadata_filters") == {"tenant_id": "tenant-1", "category": "norms"}
    assert captured.get("tenant") == "tenant-1"
