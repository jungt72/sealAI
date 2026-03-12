from __future__ import annotations

import pytest


def test_hybrid_fusion_prefers_bm25_when_vector_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0]])
    monkeypatch.setattr(
        ro,
        "_qdrant_search_with_retry",
        lambda *_args, **_kwargs: ([], {"attempts": 1, "timeout_s": 5.0, "elapsed_ms": 1, "retry_backoff_ms": None, "error": None}),
    )
    monkeypatch.setattr(
        ro,
        "_bm25_search",
        lambda *_args, **_kwargs: ([
            {
                "text": "DIN 3760 Ra 0.4",
                "sparse_score": 10.0,
                "metadata": {"document_id": "doc-1", "chunk_index": 0, "tenant_id": "tenant-1"},
            }
        ], None),
    )
    monkeypatch.setattr(ro, "_fallback_external_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ro, "USE_BM25", True)

    hits, meta = ro.hybrid_retrieve(
        query="DIN 3760 Ra 0.4",
        tenant="tenant-1",
        k=1,
        use_rerank=False,
        return_metrics=True,
    )

    assert hits
    assert hits[0]["metadata"]["document_id"] == "doc-1"
    hybrid = meta.get("hybrid") or {}
    assert hybrid.get("enabled") is True
    assert hybrid.get("counts", {}).get("bm25") == 1


def test_hybrid_dedup_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    captured = {}

    def fake_qdrant(*_args, **_kwargs):
        return (
            [
                {
                    "text": "PTFE bronze",
                    "vector_score": 0.9,
                    "metadata": {"document_id": "doc-2", "chunk_index": 1, "tenant_id": "tenant-1"},
                }
            ],
            {"attempts": 1, "timeout_s": 5.0, "elapsed_ms": 1, "retry_backoff_ms": None, "error": None},
        )

    def fake_bm25(_query, _collection, top_k=6, metadata_filters=None):
        captured["filters"] = metadata_filters
        return (
            [
                {
                    "text": "PTFE bronze",
                    "sparse_score": 12.0,
                    "metadata": {"document_id": "doc-2", "chunk_index": 1, "tenant_id": "tenant-1"},
                }
            ],
            None,
        )

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0]])
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_qdrant)
    monkeypatch.setattr(ro, "_bm25_search", fake_bm25)
    monkeypatch.setattr(ro, "_fallback_external_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ro, "USE_BM25", True)

    hits, meta = ro.hybrid_retrieve(
        query="PTFE bronze",
        tenant="tenant-1",
        k=3,
        use_rerank=False,
        return_metrics=True,
        metadata_filters={"tenant_id": "tenant-1"},
    )

    assert captured.get("filters") == {"tenant_id": "tenant-1", "_visibility_user_id": "tenant-1"}
    assert len(hits) == 1
    hybrid = meta.get("hybrid") or {}
    assert hybrid.get("overlap") == 1


def test_hybrid_retrieve_applies_bm25_metadata_filters_as_and(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0]])
    monkeypatch.setattr(
        ro,
        "_qdrant_search_with_retry",
        lambda *_args, **_kwargs: (
            [],
            {"attempts": 1, "timeout_s": 5.0, "elapsed_ms": 1, "retry_backoff_ms": None, "error": None},
        ),
    )
    monkeypatch.setattr(
        ro,
        "_bm25_search",
        lambda *_args, **_kwargs: (
            [
                {
                    "text": "norm hit",
                    "sparse_score": 12.0,
                    "metadata": {
                        "document_id": "doc-1",
                        "tenant_id": "tenant-1",
                        "route_key": "standard_or_norm",
                        "category": "norms",
                        "source_system": "paperless",
                        "tags": ["norm", "knowledge"],
                    },
                },
                {
                    "text": "wrong route",
                    "sparse_score": 11.0,
                    "metadata": {
                        "document_id": "doc-2",
                        "tenant_id": "tenant-1",
                        "route_key": "technical_knowledge",
                        "category": "norms",
                        "source_system": "paperless",
                        "tags": ["norm"],
                    },
                },
                {
                    "text": "wrong tags",
                    "sparse_score": 10.0,
                    "metadata": {
                        "document_id": "doc-3",
                        "tenant_id": "tenant-1",
                        "route_key": "standard_or_norm",
                        "category": "norms",
                        "source_system": "paperless",
                        "tags": ["supplier"],
                    },
                },
            ],
            None,
        ),
    )
    monkeypatch.setattr(ro, "_fallback_external_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ro, "USE_BM25", True)

    hits, meta = ro.hybrid_retrieve(
        query="DIN 3760",
        tenant="tenant-1",
        k=3,
        use_rerank=False,
        return_metrics=True,
        metadata_filters={
            "route_key": "standard_or_norm",
            "category": "norms",
            "source_system": "paperless",
            "tags": ["norm", "knowledge"],
        },
    )

    assert len(hits) == 1
    assert hits[0]["metadata"]["document_id"] == "doc-1"
    hybrid = meta.get("hybrid") or {}
    assert hybrid.get("counts", {}).get("bm25") == 1


def test_hybrid_retrieve_filters_zero_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0]])
    monkeypatch.setattr(
        ro,
        "_qdrant_search_with_retry",
        lambda *_args, **_kwargs: (
            [
                {
                    "text": "irrelevant-zero",
                    "vector_score": 0.0,
                    "metadata": {"document_id": "doc-0", "chunk_index": 0, "tenant_id": "tenant-1"},
                }
            ],
            {"attempts": 1, "timeout_s": 5.0, "elapsed_ms": 1, "retry_backoff_ms": None, "error": None},
        ),
    )
    monkeypatch.setattr(
        ro,
        "_bm25_search",
        lambda *_args, **_kwargs: (
            [
                {
                    "text": "irrelevant-zero-bm25",
                    "sparse_score": 0.0,
                    "metadata": {"document_id": "doc-1", "chunk_index": 0, "tenant_id": "tenant-1"},
                }
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        ro,
        "_fallback_external_search",
        lambda *_args, **_kwargs: [
            {
                "text": "low-quality",
                "vector_score": 0.0,
                "metadata": {"document_id": "doc-2"},
            }
        ],
    )
    monkeypatch.setattr(ro, "USE_BM25", True)

    hits, meta = ro.hybrid_retrieve(
        query="unmatched query",
        tenant="tenant-1",
        k=3,
        use_rerank=False,
        return_metrics=True,
    )

    assert hits == []
    assert meta.get("k_returned") == 0
    assert meta.get("top_scores") == []
