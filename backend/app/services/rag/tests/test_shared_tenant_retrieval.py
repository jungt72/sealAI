from __future__ import annotations

import importlib
import sys
import types


def _install_fastembed_stub() -> None:
    if "langchain_community" not in sys.modules:
        sys.modules["langchain_community"] = types.ModuleType("langchain_community")
    if "langchain_community.embeddings" not in sys.modules:
        sys.modules["langchain_community.embeddings"] = types.ModuleType("langchain_community.embeddings")
    if "langchain_community.embeddings.fastembed" not in sys.modules:
        fastembed_mod = types.ModuleType("langchain_community.embeddings.fastembed")

        class _StubFastEmbedEmbeddings:
            def __init__(self, *args, **kwargs):
                return None

            def embed_documents(self, texts):
                return [[0.0, 0.0, 0.0] for _ in texts]

            def embed_query(self, text):
                return [0.0, 0.0, 0.0]

        fastembed_mod.FastEmbedEmbeddings = _StubFastEmbedEmbeddings
        sys.modules["langchain_community.embeddings.fastembed"] = fastembed_mod


def _import_orchestrator():
    _install_fastembed_stub()
    module_name = "app.services.rag.rag_orchestrator"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def test_shared_tenant_enabled_builds_should_filter(monkeypatch):
    monkeypatch.setenv("RAG_SHARED_TENANT_ENABLED", "1")
    monkeypatch.setenv("RAG_SHARED_TENANT_ID", "default")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "3")
    ro = _import_orchestrator()

    def _fake_embed(_texts):
        return [[0.0, 0.0, 0.0]]

    def _fake_qdrant_search(query_vec, collection, top_k, metadata_filters=None, qdrant_filter=None):
        assert qdrant_filter is not None
        assert qdrant_filter.get("should") is None
        min_should = qdrant_filter.get("min_should") or {}
        assert min_should.get("min_count") == 1
        should = min_should.get("conditions") or []
        assert any(
            clause.get("must", [{}])[0].get("match", {}).get("value") == "tenant-1"
            for clause in should
        )
        assert any(
            clause.get("must", [{}])[0].get("match", {}).get("value") == "default"
            for clause in should
        )
        shared_clause = next(
            clause for clause in should
            if clause.get("must", [{}])[0].get("match", {}).get("value") == "default"
        )
        assert any(
            item.get("key") == "metadata.visibility"
            and item.get("match", {}).get("value") == "public"
            for item in shared_clause.get("must", [])
        )
        return (
            [
                {
                    "text": "Kyrolon info",
                    "metadata": {"tenant_id": "default", "document_id": "doc-1", "filename": "PTFE_Kyrolon.txt"},
                }
            ],
            {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "retry_backoff_ms": None, "error": None},
        )

    monkeypatch.setattr(ro, "_embed", _fake_embed, raising=False)
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", _fake_qdrant_search, raising=False)

    hits, meta = ro.hybrid_retrieve(
        query="Kyrolon",
        tenant="tenant-1",
        k=1,
        metadata_filters={"category": "norms"},
        return_metrics=True,
    )
    assert hits
    assert meta["shared_fallback"]["used"] is True


def test_shared_tenant_disabled_uses_tenant_only(monkeypatch):
    monkeypatch.setenv("RAG_SHARED_TENANT_ENABLED", "0")
    monkeypatch.setenv("RAG_SHARED_TENANT_ID", "default")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "3")
    ro = _import_orchestrator()

    def _fake_embed(_texts):
        return [[0.0, 0.0, 0.0]]

    def _fake_qdrant_search(query_vec, collection, top_k, metadata_filters=None, qdrant_filter=None):
        assert qdrant_filter is not None
        assert qdrant_filter.get("should") is None
        must = qdrant_filter.get("must") or []
        assert any(
            item.get("key") == "metadata.tenant_id"
            and item.get("match", {}).get("value") == "tenant-1"
            for item in must
        )
        return (
            [
                {
                    "text": "Tenant info",
                    "metadata": {"tenant_id": "tenant-1", "document_id": "doc-2", "filename": "tenant.txt"},
                }
            ],
            {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "retry_backoff_ms": None, "error": None},
        )

    monkeypatch.setattr(ro, "_embed", _fake_embed, raising=False)
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", _fake_qdrant_search, raising=False)

    hits, meta = ro.hybrid_retrieve(
        query="Kyrolon",
        tenant="tenant-1",
        k=1,
        metadata_filters={"category": "norms"},
        return_metrics=True,
    )
    assert hits
    assert meta["shared_fallback"]["used"] is False
