from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace


class _DummyDoc:
    def __init__(self, text: str) -> None:
        self.page_content = text
        self.metadata = {}


class _DummySplitter:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def split_documents(self, docs):
        return docs


class _DummyEmbeddings:
    def __init__(self, *args, **kwargs) -> None:
        return None


def _import_rag_ingest():
    dummy_module = ModuleType("langchain_qdrant")
    dummy_module.QdrantVectorStore = SimpleNamespace(from_documents=lambda *args, **kwargs: None)
    sys.modules["langchain_qdrant"] = dummy_module
    splitters = ModuleType("langchain_text_splitters")
    splitters.RecursiveCharacterTextSplitter = _DummySplitter
    sys.modules["langchain_text_splitters"] = splitters
    hf_module = ModuleType("langchain_huggingface")
    hf_module.HuggingFaceEmbeddings = _DummyEmbeddings
    sys.modules["langchain_huggingface"] = hf_module
    community = ModuleType("langchain_community")
    loaders = ModuleType("langchain_community.document_loaders")
    loaders.PDFPlumberLoader = object
    loaders.Docx2txtLoader = object
    loaders.TextLoader = object
    loaders.UnstructuredFileLoader = object
    sys.modules["langchain_community"] = community
    sys.modules["langchain_community.document_loaders"] = loaders
    sys.modules.pop("app.services.rag.rag_ingest", None)
    return importlib.import_module("app.services.rag.rag_ingest")


def test_rag_ingest_passes_deterministic_point_ids(monkeypatch, tmp_path) -> None:
    rag_ingest = _import_rag_ingest()
    captured = {"ids": []}

    def fake_from_documents(*args, **kwargs):
        captured["ids"].append(kwargs.get("ids"))
        captured["collection_name"] = kwargs.get("collection_name")
        captured["docs_len"] = len(args[0])
        return None

    monkeypatch.setattr(rag_ingest, "QDRANT_COLLECTION", "sealai-docs")
    monkeypatch.setattr(rag_ingest, "QDRANT_COLLECTION_PREFIX", "rag")
    monkeypatch.setattr(rag_ingest, "RecursiveCharacterTextSplitter", _DummySplitter)
    monkeypatch.setattr(rag_ingest, "HuggingFaceEmbeddings", _DummyEmbeddings)
    monkeypatch.setattr(rag_ingest, "QdrantVectorStore", SimpleNamespace(from_documents=fake_from_documents))
    monkeypatch.setattr(
        rag_ingest,
        "load_document",
        lambda _path: [_DummyDoc("hello"), _DummyDoc("world")],
    )

    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello world", encoding="utf-8")

    rag_ingest.ingest_file(str(file_path), tenant_id="tenant-1")
    rag_ingest.ingest_file(str(file_path), tenant_id="tenant-1")

    assert captured["collection_name"] == "rag:tenant-1"
    assert len(captured["ids"]) == 2
    first_ids, second_ids = captured["ids"]
    assert first_ids == second_ids
    assert len(first_ids) == captured["docs_len"]
