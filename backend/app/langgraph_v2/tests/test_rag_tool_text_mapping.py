from app.langgraph_v2.utils import rag_tool


def test_rag_tool_uses_page_content_when_text_missing(monkeypatch) -> None:
    def fake_retrieve(**_kwargs):
        return [
            {
                "text": "",
                "page_content": "Kyrolon material details",
                "metadata": {"document_id": "doc-1", "filename": "PTFE_Kyrolon.txt"},
            }
        ], {"k_returned": 1}

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", fake_retrieve)
    payload = rag_tool.search_knowledge_base.invoke(
        {
            "query": "Kyrolon",
            "category": "norms",
            "k": 1,
            "tenant": "tenant-1",
            "can_read_private": False,
        }
    )
    assert "Kyrolon material details" in payload.get("context", "")
