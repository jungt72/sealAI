from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

pytestmark = pytest.mark.skip(reason="legacy metadata loader contract replaced by point-based ingest pipeline")


def test_ingest_file_enriches_metadata(monkeypatch, tmp_path: Path) -> None:
    if "langchain_qdrant" not in sys.modules:
        qdrant_stub = types.ModuleType("langchain_qdrant")

        class _StubQdrantVectorStore:
            @staticmethod
            def from_documents(*_args, **_kwargs):
                return None

        qdrant_stub.QdrantVectorStore = _StubQdrantVectorStore
        sys.modules["langchain_qdrant"] = qdrant_stub

    if "langchain_community.embeddings.fastembed" not in sys.modules:
        hf_stub = types.ModuleType("langchain_community.embeddings.fastembed")

        class _StubEmbeddings:
            def __init__(self, *args, **kwargs):
                return None

        hf_stub.FastEmbedEmbeddings = _StubEmbeddings
        sys.modules["langchain_community.embeddings.fastembed"] = hf_stub

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

    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "jinaai/jina-embeddings-v2-base-de")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "768")

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
    monkeypatch.setattr(rag_ingest, "get_embedder", lambda: DummyEmbeddings())
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


def test_docx_fallback_uses_python_docx(monkeypatch, tmp_path: Path) -> None:
    if "langchain_qdrant" not in sys.modules:
        qdrant_stub = types.ModuleType("langchain_qdrant")

        class _StubQdrantVectorStore:
            @staticmethod
            def from_documents(*_args, **_kwargs):
                return None

        qdrant_stub.QdrantVectorStore = _StubQdrantVectorStore
        sys.modules["langchain_qdrant"] = qdrant_stub

    if "langchain_community.embeddings.fastembed" not in sys.modules:
        hf_stub = types.ModuleType("langchain_community.embeddings.fastembed")

        class _StubEmbeddings:
            def __init__(self, *args, **kwargs):
                return None

        hf_stub.FastEmbedEmbeddings = _StubEmbeddings
        sys.modules["langchain_community.embeddings.fastembed"] = hf_stub

    if "langchain_text_splitters" not in sys.modules:
        split_stub = types.ModuleType("langchain_text_splitters")

        class _StubSplitter:
            def __init__(self, *args, **kwargs):
                return None

            def split_documents(self, docs):
                return docs

        split_stub.RecursiveCharacterTextSplitter = _StubSplitter
        sys.modules["langchain_text_splitters"] = split_stub

    from app.services.rag import rag_ingest

    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "jinaai/jina-embeddings-v2-base-de")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "768")

    class DummyQdrant:
        @staticmethod
        def from_documents(*_args, **_kwargs):
            return None

    class DummyEmbeddings:
        def __init__(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr(rag_ingest, "QdrantVectorStore", DummyQdrant)
    monkeypatch.setattr(rag_ingest, "get_embedder", lambda: DummyEmbeddings())
    class FailingDocxLoader:
        def __init__(self, *args, **kwargs):
            return None

        def load(self):
            raise RuntimeError("docx_loader_unavailable")

    monkeypatch.setattr(rag_ingest, "Docx2txtLoader", FailingDocxLoader)

    if "docx" not in sys.modules:
        docx_stub = types.ModuleType("docx")

        class _Paragraph:
            def __init__(self, text: str) -> None:
                self.text = text

        class _StubDocument:
            def __init__(self, _path: str | None = None) -> None:
                self.paragraphs = [_Paragraph("PTFE Datenblatt Text")]

        docx_stub.Document = _StubDocument
        sys.modules["docx"] = docx_stub

    docx_path = tmp_path / "ptfe.docx"
    docx_path.write_text("ptfe", encoding="utf-8")

    stats = rag_ingest.ingest_file(
        str(docx_path),
        tenant_id="tenant-1",
        document_id="doc-ptfe",
        category="specs",
        tags=["ptfe"],
        visibility="private",
        sha256="hash-ptfe",
        source="upload",
    )
    assert isinstance(stats, dict)
    assert stats.get("loader") == "python-docx"
    assert stats.get("chunks") == 1


def test_ingest_requires_tenant_id(monkeypatch, tmp_path: Path) -> None:
    if "langchain_qdrant" not in sys.modules:
        qdrant_stub = types.ModuleType("langchain_qdrant")

        class _StubQdrantVectorStore:
            @staticmethod
            def from_documents(*_args, **_kwargs):
                return None

        qdrant_stub.QdrantVectorStore = _StubQdrantVectorStore
        sys.modules["langchain_qdrant"] = qdrant_stub

    if "langchain_community.embeddings.fastembed" not in sys.modules:
        hf_stub = types.ModuleType("langchain_community.embeddings.fastembed")

        class _StubEmbeddings:
            def __init__(self, *args, **kwargs):
                return None

        hf_stub.FastEmbedEmbeddings = _StubEmbeddings
        sys.modules["langchain_community.embeddings.fastembed"] = hf_stub

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

    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "jinaai/jina-embeddings-v2-base-de")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "768")

    called = {"qdrant": False}

    class DummyQdrant:
        @staticmethod
        def from_documents(*_args, **_kwargs):
            called["qdrant"] = True
            return None

    class DummyEmbeddings:
        def __init__(self, *args, **kwargs) -> None:
            return None

    def fake_load_document(file_path: str):
        return [Document(page_content="Spec text", metadata={})]

    monkeypatch.setattr(rag_ingest, "QdrantVectorStore", DummyQdrant)
    monkeypatch.setattr(rag_ingest, "get_embedder", lambda: DummyEmbeddings())
    monkeypatch.setattr(rag_ingest, "load_document", fake_load_document)

    file_path = tmp_path / "doc.txt"
    file_path.write_text("Spec text", encoding="utf-8")

    try:
        rag_ingest.ingest_file(str(file_path), tenant_id=" ")
    except ValueError as exc:
        assert "tenant_id" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing tenant_id")

    assert called["qdrant"] is False
