from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def _install_stub_module(name: str, attrs: dict[str, object]) -> None:
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules.setdefault(name, module)


def _install_rag_ingest_stubs() -> None:
    class Dummy:
        def __init__(self, *args, **kwargs):
            pass

    class DummyVectorStore:
        def __init__(self, *args, **kwargs):
            pass

        @classmethod
        def from_documents(cls, *_args, **_kwargs):
            return None

    _install_stub_module("langchain_qdrant", {"QdrantVectorStore": DummyVectorStore})
    _install_stub_module("langchain_text_splitters", {"RecursiveCharacterTextSplitter": Dummy})
    _install_stub_module(
        "langchain_community.document_loaders",
        {
            "PDFPlumberLoader": Dummy,
            "Docx2txtLoader": Dummy,
            "TextLoader": Dummy,
            "UnstructuredFileLoader": Dummy,
        },
    )


def test_qdrant_collection_is_single(monkeypatch):
    from app.services.rag import rag_orchestrator as ro

    monkeypatch.setenv("QDRANT_COLLECTION", "sealai_knowledge")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "384")
    monkeypatch.setattr(ro, "QDRANT_COLLECTION_DEFAULT", "sealai_knowledge", raising=False)

    captured = {}

    def fake_search(_vec, collection, top_k=0, metadata_filters=None):
        captured["collection"] = collection
        return [], {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "error": None}

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)
    _ = ro.hybrid_retrieve(
        query="x", tenant="tenant-1", k=1, metadata_filters={"metadata.tenant_id": "tenant-1"}
    )
    assert captured.get("collection") == "sealai_knowledge"


def test_hybrid_retrieve_requires_tenant(monkeypatch):
    from app.services.rag import rag_orchestrator as ro

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])
    with pytest.raises(ValueError):
        _ = ro.hybrid_retrieve(query="x", tenant=None, k=1, metadata_filters={})


def test_hybrid_retrieve_injects_tenant_filter(monkeypatch):
    from app.services.rag import rag_orchestrator as ro

    captured = {}

    def fake_search(_vec, _collection, top_k=0, metadata_filters=None):
        captured["filters"] = metadata_filters or {}
        return [], {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "error": None}

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)

    _ = ro.hybrid_retrieve(query="x", tenant="tenant-1", k=1, metadata_filters={"category": "norms"})

    assert captured["filters"]["metadata.tenant_id"] == "tenant-1"
    assert captured["filters"]["category"] == "norms"


def test_hybrid_retrieve_injects_tenant_filter_when_none(monkeypatch):
    from app.services.rag import rag_orchestrator as ro

    captured = {}

    def fake_search(_vec, _collection, top_k=0, metadata_filters=None):
        captured["filters"] = metadata_filters or {}
        return [], {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "error": None}

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)

    _ = ro.hybrid_retrieve(query="x", tenant="tenant-1", k=1, metadata_filters=None)

    assert captured["filters"] == {"metadata.tenant_id": "tenant-1"}


def test_hybrid_retrieve_normalizes_legacy_filters(monkeypatch):
    from app.services.rag import rag_orchestrator as ro

    captured = {}

    def fake_search(_vec, _collection, top_k=0, metadata_filters=None):
        captured["filters"] = metadata_filters or {}
        return (
            [{"text": "ok", "vector_score": 0.9, "metadata": {"metadata": {"tenant_id": "tenant-1"}}}],
            {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "error": None},
        )

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)

    hits = ro.hybrid_retrieve(
        query="x",
        tenant="tenant-1",
        k=1,
        metadata_filters={
            "tenant_id": "tenant-1",
            "metadata.tenant_id": "tenant-1",
            "document_id": "doc-1",
        },
        use_rerank=False,
    )

    assert hits
    assert captured["filters"].get("metadata.tenant_id") == "tenant-1"
    assert captured["filters"].get("metadata.document_id") == "doc-1"
    assert "tenant_id" not in captured["filters"]
    assert "document_id" not in captured["filters"]


def test_hybrid_retrieve_rejects_tenant_filter_mismatch(monkeypatch):
    from app.services.rag import rag_orchestrator as ro

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])

    with pytest.raises(ValueError):
        _ = ro.hybrid_retrieve(
            query="x", tenant="tenant-1", k=1, metadata_filters={"metadata.tenant_id": "tenant-2"}
        )


def test_build_sources_derives_filename_from_source_path():
    from app.services.rag import rag_orchestrator as ro

    hits = [
        {
            "metadata": {
                "document_id": "doc-1",
                "source": "/app/data/uploads/tenant-1/doc-1/original.txt",
            }
        }
    ]

    sources = ro._build_sources(hits)

    assert sources[0]["filename"] == "original.txt"
    assert sources[0]["source"] == "/app/data/uploads/tenant-1/doc-1/original.txt"


def test_ingest_and_retrieve_use_same_collection(monkeypatch, tmp_path):
    _install_rag_ingest_stubs()
    from app.services.rag import rag_ingest, rag_orchestrator as ro

    monkeypatch.setenv("QDRANT_COLLECTION", "sealai_knowledge")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "384")
    monkeypatch.setattr(rag_ingest, "QDRANT_COLLECTION", "sealai_knowledge", raising=False)
    monkeypatch.setattr(ro, "QDRANT_COLLECTION_DEFAULT", "sealai_knowledge", raising=False)

    captured = {"ingest": None, "retrieve": None}

    class DummyDoc:
        def __init__(self):
            self.metadata = {}

    def fake_load_document(_path):
        return [DummyDoc()]

    class FakeSplitter:
        def __init__(self, *args, **kwargs):
            pass

        def split_documents(self, _docs):
            return []

    class FakeEmbeddings:
        def __init__(self, *args, **kwargs):
            pass

    def fake_from_documents(_docs, _embeddings, *, url=None, api_key=None, collection_name=None):
        captured["ingest"] = collection_name
        return None

    def fake_search(_vec, collection, top_k=0, metadata_filters=None):
        captured["retrieve"] = collection
        return [], {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "error": None}

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])
    monkeypatch.setattr(rag_ingest, "load_document", fake_load_document)
    monkeypatch.setattr(rag_ingest, "RecursiveCharacterTextSplitter", FakeSplitter)
    monkeypatch.setattr(rag_ingest, "get_embedder", lambda: FakeEmbeddings())
    monkeypatch.setattr(rag_ingest.QdrantVectorStore, "from_documents", fake_from_documents)
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)

    file_path = tmp_path / "doc.txt"
    file_path.write_text("test")

    rag_ingest.ingest_file(str(file_path), tenant_id="tenant-1", document_id="doc-1")
    _ = ro.hybrid_retrieve(
        query="x", tenant="tenant-1", k=1, metadata_filters={"metadata.tenant_id": "tenant-1"}
    )

    assert captured["ingest"] == "sealai_knowledge"
    assert captured["retrieve"] == "sealai_knowledge"
