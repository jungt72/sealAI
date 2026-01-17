from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

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
    _install_stub_module("langchain_huggingface", {"HuggingFaceEmbeddings": Dummy})
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
    monkeypatch.setattr(ro, "QDRANT_COLLECTION_DEFAULT", "sealai_knowledge", raising=False)

    captured = {}

    def fake_search(_vec, collection, top_k=0, metadata_filters=None):
        captured["collection"] = collection
        return [], {"attempts": 1, "timeout_s": 1, "elapsed_ms": 0, "error": None}

    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0, 0.0, 0.0]])
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)
    _ = ro.hybrid_retrieve(query="x", tenant="tenant-1", k=1, metadata_filters={"tenant_id": "tenant-1"})
    assert captured.get("collection") == "sealai_knowledge"


def test_ingest_and_retrieve_use_same_collection(monkeypatch, tmp_path):
    _install_rag_ingest_stubs()
    from app.services.rag import rag_ingest, rag_orchestrator as ro

    monkeypatch.setenv("QDRANT_COLLECTION", "sealai_knowledge")
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
    monkeypatch.setattr(rag_ingest, "HuggingFaceEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(rag_ingest.QdrantVectorStore, "from_documents", fake_from_documents)
    monkeypatch.setattr(ro, "_qdrant_search_with_retry", fake_search)

    file_path = tmp_path / "doc.txt"
    file_path.write_text("test")

    rag_ingest.ingest_file(str(file_path), tenant_id="tenant-1", document_id="doc-1")
    _ = ro.hybrid_retrieve(query="x", tenant="tenant-1", k=1, metadata_filters={"tenant_id": "tenant-1"})

    assert captured["ingest"] == "sealai_knowledge"
    assert captured["retrieve"] == "sealai_knowledge"
