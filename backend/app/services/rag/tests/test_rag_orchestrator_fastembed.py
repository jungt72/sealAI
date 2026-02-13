from __future__ import annotations

import importlib
import os
import sys
import types

import pytest


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


def test_import_does_not_pull_sentence_transformers_or_torch(monkeypatch):
    sys.modules.pop("sentence_transformers", None)
    sys.modules.pop("torch", None)
    _ = _import_orchestrator()
    assert "sentence_transformers" not in sys.modules
    assert "torch" not in sys.modules


def test_resolve_embedding_config_prefers_embedder_dim_without_env(monkeypatch):
    ro = _import_orchestrator()
    monkeypatch.delenv("RAG_EMBEDDING_DIM", raising=False)
    monkeypatch.setattr(ro, "_embedding_dim", None, raising=False)

    class _Embedder:
        embedding_dimension = 384

    monkeypatch.setattr(ro, "_embedder", _Embedder(), raising=False)

    def _no_probe(_texts):
        raise AssertionError("resolve_embedding_config should not probe embeddings when dim is known")

    monkeypatch.setattr(ro, "_embed", _no_probe, raising=False)
    model_name, dim = ro.resolve_embedding_config()
    assert model_name
    assert dim == 384


def test_resolve_embedding_config_falls_back_to_env_and_validates(monkeypatch):
    ro = _import_orchestrator()
    monkeypatch.setattr(ro, "_embedding_dim", None, raising=False)

    class _UnknownEmbedder:
        pass

    monkeypatch.setattr(ro, "_embedder", _UnknownEmbedder(), raising=False)

    def _no_probe(_texts):
        raise AssertionError("resolve_embedding_config should not probe embeddings when RAG_EMBEDDING_DIM is set")

    monkeypatch.setattr(ro, "_embed", _no_probe, raising=False)

    monkeypatch.setenv("RAG_EMBEDDING_DIM", "384")
    _model_name, dim = ro.resolve_embedding_config()
    assert dim == 384

    for value in ("0", "-1", "abc"):
        monkeypatch.setattr(ro, "_embedding_dim", None, raising=False)
        monkeypatch.setenv("RAG_EMBEDDING_DIM", value)
        with pytest.raises(ValueError) as excinfo:
            ro.resolve_embedding_config()
        assert "EMBEDDING_DIM" in str(excinfo.value)


def test_rerank_is_noop_when_enabled(monkeypatch):
    ro = _import_orchestrator()
    sys.modules.pop("sentence_transformers", None)
    sys.modules.pop("torch", None)

    hits = [
        {"text": "a", "vector_score": 0.9},
        {"text": "b", "vector_score": 0.8},
        {"text": "c", "vector_score": 0.7},
    ]

    if hasattr(ro, "_rerank_if_enabled"):
        out = ro._rerank_if_enabled("q", list(hits), use_rerank=True)
    else:
        monkeypatch.setattr(ro, "_embed", lambda _t: [[0.0, 0.0, 0.0]])
        monkeypatch.setattr(
            ro,
            "_qdrant_search_with_retry",
            lambda *_args, **_kwargs: (list(hits), {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "error": None}),
        )
        out = ro.hybrid_retrieve(
            query="q", tenant="tenant-1", k=3, metadata_filters={"metadata.tenant_id": "tenant-1"}
        )

    assert [h.get("text") for h in out] == [h.get("text") for h in hits]
    assert "sentence_transformers" not in sys.modules
    assert "torch" not in sys.modules


def test_sentence_transformers_provider_missing_dependency(monkeypatch):
    ro = _import_orchestrator()
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "sentence_transformers")
    monkeypatch.setattr(ro, "_embedder", None, raising=False)
    sys.modules.pop("sentence_transformers", None)

    with pytest.raises(ImportError) as excinfo:
        ro.get_embedder()

    assert "sentence-transformers" in str(excinfo.value)


def test_qdrant_search_falls_back_to_named_dense_vector_when_env_blank(monkeypatch):
    ro = _import_orchestrator()
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"result": []}

    class _FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse()

    fake_httpx = types.ModuleType("httpx")
    fake_httpx.Client = _FakeClient
    fake_httpx.TimeoutException = RuntimeError
    fake_httpx.TransportError = RuntimeError
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setattr(ro, "QDRANT_VECTOR_NAME", "", raising=False)

    hits, meta = ro._qdrant_search_with_retry([0.1, 0.2, 0.3], "sealai_knowledge_v3", top_k=1)
    assert hits == []
    assert meta["error"] is None
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["vector"] == {"name": "dense", "vector": [0.1, 0.2, 0.3]}


def test_hybrid_retrieve_raises_on_embedding_dim_mismatch(monkeypatch):
    ro = _import_orchestrator()
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "768")
    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]], raising=False)
    monkeypatch.setattr(
        ro,
        "_qdrant_search_with_retry",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("qdrant should not be called")),
        raising=False,
    )

    with pytest.raises(ValueError, match="rag_query_embedding_dim_mismatch"):
        ro.hybrid_retrieve(query="kyrolon", tenant="tenant-1", k=3)
