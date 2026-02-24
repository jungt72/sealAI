from __future__ import annotations


def test_hybrid_retrieve_adds_sources(monkeypatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    def fake_embed(_texts):
        return [[0.0, 0.0]]

    def fake_search(_query_vec, _sparse_query, _collection, top_k=6, metadata_filters=None, timeout_s=None):
        hits = [
            {
                "text": "A",
                "vector_score": 0.9,
                "metadata": {
                    "document_id": "doc-1",
                    "sha256": "hash-1",
                    "filename": "specs.pdf",
                    "page": 2,
                    "section_title": "Werkstoffe",
                    "source": "upload",
                },
            },
            {
                "text": "B",
                "vector_score": 0.7,
                "metadata": {
                    "doc_id": "doc-2",
                    "page_number": "3",
                    "file": "legacy",
                },
            },
        ]
        return hits, {"attempts": 1, "timeout_s": 5.0, "elapsed_ms": 1, "retry_backoff_ms": None, "error": None}

    monkeypatch.setattr(ro, "_embed", fake_embed)
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)

    _results, metrics = ro.hybrid_retrieve(
        query="test",
        tenant="tenant-1",
        k=2,
        use_rerank=False,
        return_metrics=True,
    )

    sources = metrics.get("sources") or []
    assert sources, "Expected sources in retrieval metrics."
    assert sources[0]["document_id"] == "doc-1"
    assert sources[0]["page"] == 2
    assert sources[0]["section"] == "Werkstoffe"
    assert sources[1]["document_id"] == "doc-2"
    assert sources[1]["page"] == 3
