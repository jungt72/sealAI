from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import types


def test_ingest_file_enriches_metadata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RAG_INGEST_LEGACY_VECTORSTORE", "1")
    if "langchain_qdrant" not in sys.modules:
        qdrant_stub = types.ModuleType("langchain_qdrant")

        class _StubQdrantVectorStore:
            @staticmethod
            def from_documents(*_args, **_kwargs):
                return None

        qdrant_stub.QdrantVectorStore = _StubQdrantVectorStore
        sys.modules["langchain_qdrant"] = qdrant_stub

    if "langchain_huggingface" not in sys.modules:
        hf_stub = types.ModuleType("langchain_huggingface")

        class _StubEmbeddings:
            def __init__(self, *args, **kwargs):
                return None

        hf_stub.HuggingFaceEmbeddings = _StubEmbeddings
        sys.modules["langchain_huggingface"] = hf_stub

    if "langchain_text_splitters" not in sys.modules:
        split_stub = types.ModuleType("langchain_text_splitters")

        class _StubSplitter:
            def __init__(self, *args, **kwargs):
                return None

            def split_documents(self, docs):
                return docs

        split_stub.RecursiveCharacterTextSplitter = _StubSplitter
        sys.modules["langchain_text_splitters"] = split_stub

    if "langchain_community.document_loaders" not in sys.modules:
        loaders_stub = types.ModuleType("langchain_community.document_loaders")

        class _StubLoader:
            def __init__(self, *args, **kwargs):
                return None

            def load(self):
                return []

        loaders_stub.PDFPlumberLoader = _StubLoader
        loaders_stub.Docx2txtLoader = _StubLoader
        loaders_stub.TextLoader = _StubLoader
        loaders_stub.UnstructuredFileLoader = _StubLoader
        sys.modules["langchain_community.document_loaders"] = loaders_stub

    from langchain_core.documents import Document

    from app.services.rag import rag_ingest

    captured = {}

    class DummyQdrant:
        @staticmethod
        def from_documents(docs, embeddings, url=None, api_key=None, collection_name=None):
            captured["docs"] = docs
            captured["collection_name"] = collection_name
            return None

    class DummyEmbeddings:
        def __init__(self, *args, **kwargs) -> None:
            return None

    def fake_load_document(file_path: str):
        return [
            Document(
                page_content="Spec text",
                metadata={"page": 1, "section_title": "Einleitung"},
            )
        ]

    monkeypatch.setattr(rag_ingest, "QdrantVectorStore", DummyQdrant)
    monkeypatch.setattr(rag_ingest, "HuggingFaceEmbeddings", DummyEmbeddings)
    monkeypatch.setattr(rag_ingest, "load_document", fake_load_document)

    file_path = tmp_path / "doc.txt"
    file_path.write_text("Spec text", encoding="utf-8")

    rag_ingest.ingest_file(
        str(file_path),
        tenant_id="tenant-1",
        document_id="doc-1",
        category="specs",
        tags=["a", "b"],
        visibility="private",
        sha256="hash-1",
        source="upload",
        route_key="general_technical_doc",
        source_system="paperless",
        source_document_id="paperless-11",
        source_modified_at=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
    )

    docs = captured.get("docs") or []
    assert docs, "Expected Qdrant upsert to receive documents."
    meta = docs[0].metadata
    assert meta.get("filename") == "doc.txt"
    assert meta.get("content_type") == "text/plain"
    assert meta.get("size_bytes") == file_path.stat().st_size
    assert meta.get("source_path") == "doc.txt"
    assert meta.get("page") == 1
    assert meta.get("section") == "Einleitung"
    assert meta.get("category") == "specs"
    assert meta.get("route_key") == "general_technical_doc"
    assert meta.get("tags") == ["a", "b"]
    assert meta.get("source_type") == "crawl"
    assert meta.get("source_system") == "paperless"
    assert meta.get("source_document_id") == "paperless-11"
    assert meta.get("source_modified_at") == "2026-03-12T10:00:00+00:00"


def test_ingest_file_skips_empty_document_in_legacy_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RAG_INGEST_LEGACY_VECTORSTORE", "1")
    from app.services.rag import rag_ingest

    called = {"from_documents": 0}

    class DummyQdrant:
        @staticmethod
        def from_documents(*_args, **_kwargs):
            called["from_documents"] += 1
            return None

    class DummyEmbeddings:
        def __init__(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr(rag_ingest, "QdrantVectorStore", DummyQdrant)
    monkeypatch.setattr(rag_ingest, "HuggingFaceEmbeddings", DummyEmbeddings)
    monkeypatch.setattr(rag_ingest, "load_document", lambda _file_path: [])

    file_path = tmp_path / "empty.docx"
    file_path.write_text("", encoding="utf-8")

    result = rag_ingest.ingest_file(
        str(file_path),
        tenant_id="tenant-1",
        document_id="doc-empty",
        category="specs",
        route_key="general_technical_doc",
    )

    assert result["chunks"] == 0
    assert result["route_key"] == "general_technical_doc"
    assert called["from_documents"] == 0
