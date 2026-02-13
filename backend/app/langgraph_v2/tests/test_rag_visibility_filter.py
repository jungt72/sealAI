from app.langgraph_v2.utils import rag_tool


def test_rag_filters_non_admin_public_only(monkeypatch) -> None:
    captured = {}

    def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return [{"text": "hit", "metadata": {"document_id": "doc-1"}}], {"k_returned": 1}

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", fake_retrieve)
    _ = rag_tool.search_knowledge_base.invoke(
        {
            "query": "test",
            "category": "norms",
            "k": 3,
            "tenant": "tenant-1",
            "can_read_private": False,
        }
    )
    assert captured.get("metadata_filters") == {
        "metadata.domain": "norms",
        "metadata.visibility": "public",
    }


def test_rag_filters_admin_public_and_private(monkeypatch) -> None:
    captured = {}

    def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return [{"text": "hit", "metadata": {"document_id": "doc-1"}}], {"k_returned": 1}

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", fake_retrieve)
    _ = rag_tool.search_knowledge_base.invoke(
        {
            "query": "test",
            "category": "norms",
            "k": 3,
            "tenant": "tenant-1",
            "can_read_private": True,
        }
    )
    assert captured.get("metadata_filters") == {
        "metadata.domain": "norms",
    }
