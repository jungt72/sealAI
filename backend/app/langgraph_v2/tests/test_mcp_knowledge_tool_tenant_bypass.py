from app.mcp import knowledge_tool


def test_search_technical_docs_applies_tenant_scope_for_global_collection(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_COLLECTION", "sealai_knowledge_v3")
    monkeypatch.setenv("QDRANT_GLOBAL_TECH_COLLECTIONS", "sealai_knowledge_v3,sealai-docs")
    calls: list[dict] = []

    def _fake_hybrid_retrieve(**kwargs):
        calls.append(kwargs)
        return (
            [{"text": "Kyrolon data", "vector_score": 0.91, "metadata": {"source": "kyrolon.pdf"}}],
            {"k_returned": 1},
        )

    monkeypatch.setattr(knowledge_tool, "hybrid_retrieve", _fake_hybrid_retrieve)

    payload = knowledge_tool.search_technical_docs(
        query="Was ist Kyrolon?",
        tenant_id="5781c12a-c285-43f0-93ff-acaee99c9a97",
        k=3,
    )

    assert calls
    assert calls[0]["tenant"] == "5781c12a-c285-43f0-93ff-acaee99c9a97"
    assert (calls[0].get("metadata_filters") or {}).get("tenant_id") == [
        "5781c12a-c285-43f0-93ff-acaee99c9a97",
        "sealai",
    ]
    assert payload["retrieval_meta"]["tenant_scope_applied_on_global_collection"] is True
    assert len(payload["hits"]) == 1


def test_search_technical_docs_renders_table_metadata_in_context(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_COLLECTION", "sealai_knowledge_v3")
    calls: list[dict] = []

    def _fake_hybrid_retrieve(**kwargs):
        calls.append(kwargs)
        return (
            [
                {
                    "text": "PV limits for PTFE",
                    "vector_score": 0.88,
                    "metadata": {
                        "source": "ptfe.pdf",
                        "table": {
                            "columns": ["speed_m_s", "pv_limit"],
                            "rows": [{"speed_m_s": "1.0", "pv_limit": "0.8"}],
                        },
                    },
                }
            ],
            {"k_returned": 1},
        )

    monkeypatch.setattr(knowledge_tool, "hybrid_retrieve", _fake_hybrid_retrieve)

    payload = knowledge_tool.search_technical_docs(query="PV table", tenant_id="tenant-1")

    assert calls
    assert "| speed_m_s | pv_limit |" in payload["context"]
    assert "| 1.0 | 0.8 |" in payload["context"]


def test_search_technical_docs_relaxes_tenant_filter_when_needed(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_COLLECTION", "tenant-scoped-docs")
    monkeypatch.setenv("QDRANT_GLOBAL_TECH_COLLECTIONS", "sealai_knowledge_v3,sealai-docs")
    calls: list[dict] = []

    def _fake_hybrid_retrieve(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return ([], {"k_returned": 0})
        return (
            [{"text": "NBR-90 sheet", "vector_score": 0.86, "metadata": {"source": "nbr90.pdf"}}],
            {"k_returned": 1},
        )

    monkeypatch.setattr(knowledge_tool, "hybrid_retrieve", _fake_hybrid_retrieve)

    payload = knowledge_tool.search_technical_docs(
        query="Datenblatt NBR-90",
        tenant_id="5781c12a-c285-43f0-93ff-acaee99c9a97",
        k=3,
    )

    assert len(calls) == 2
    assert calls[0]["tenant"] == "5781c12a-c285-43f0-93ff-acaee99c9a97"
    assert (calls[0].get("metadata_filters") or {}).get("tenant_id") == [
        "5781c12a-c285-43f0-93ff-acaee99c9a97",
        "sealai",
    ]
    assert calls[1]["tenant"] is None
    assert "tenant_id" not in (calls[1].get("metadata_filters") or {})
    assert payload["retrieval_meta"]["tenant_filter_relaxed"] is True


def test_search_technical_docs_filters_zero_score_hits(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_COLLECTION", "sealai_knowledge_v3")

    def _fake_hybrid_retrieve(**kwargs):
        return (
            [
                {
                    "text": "false hit",
                    "vector_score": 0.0,
                    "metadata": {"source": "irrelevant.pdf"},
                }
            ],
            {"k_returned": 1, "top_scores": [0.0]},
        )

    monkeypatch.setattr(knowledge_tool, "hybrid_retrieve", _fake_hybrid_retrieve)

    payload = knowledge_tool.search_technical_docs(query="test", tenant_id="tenant-1")

    assert payload["hits"] == []
    assert payload["context"] == ""
    assert payload["retrieval_meta"]["k_returned"] == 0
    assert payload["retrieval_meta"]["top_scores"] == []
