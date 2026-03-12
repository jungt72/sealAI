from __future__ import annotations

from datetime import datetime, timezone
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

if "qdrant_client" not in sys.modules:
    qdrant_stub = types.ModuleType("qdrant_client")

    class _StubQdrantClient:
        def __init__(self, *args, **kwargs):
            return None

    qdrant_stub.QdrantClient = _StubQdrantClient

    models_mod = types.ModuleType("qdrant_client.models")

    class _PointStruct:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id")
            self.vector = kwargs.get("vector")
            self.payload = kwargs.get("payload")

    class _Filter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FieldCondition:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _MatchValue:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _SetPayload:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _SetPayloadOperation:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    models_mod.PointStruct = _PointStruct
    models_mod.Filter = _Filter
    models_mod.FieldCondition = _FieldCondition
    models_mod.MatchValue = _MatchValue
    models_mod.SetPayload = _SetPayload
    models_mod.SetPayloadOperation = _SetPayloadOperation
    qdrant_stub.models = models_mod

    http_mod = types.ModuleType("qdrant_client.http")
    http_models_mod = types.ModuleType("qdrant_client.http.models")

    class _VectorParams:
        pass

    class _SparseVectorParams:
        pass

    http_models_mod.VectorParams = _VectorParams
    http_models_mod.SparseVectorParams = _SparseVectorParams

    sys.modules["qdrant_client"] = qdrant_stub
    sys.modules["qdrant_client.models"] = models_mod
    sys.modules["qdrant_client.http"] = http_mod
    sys.modules["qdrant_client.http.models"] = http_models_mod


from app.services.rag import rag_ingest
from app.services.rag.bm25_store import bm25_repo


class _DenseVec:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class _DenseEmbedder:
    def embed(self, texts):
        return [_DenseVec([0.0, 0.0, 0.0]) for _ in texts]


def _build_pipeline():
    pipeline = rag_ingest.IngestPipeline()
    pipeline._load_embedders = lambda: None
    pipeline._dense_embedder = _DenseEmbedder()
    captured = {}

    class _DummyClient:
        def upsert(self, _collection, points):
            captured["points"] = points

    pipeline.client = _DummyClient()
    return pipeline, captured


def _capture_bm25(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def _fake_upsert_documents(_collection, docs):
        captured["docs"] = list(docs)

    monkeypatch.setattr(bm25_repo, "upsert_documents", _fake_upsert_documents, raising=False)
    return captured


@pytest.mark.anyio
async def test_pdf_extracts_text_non_empty() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"
    pages = rag_ingest._load_pages(str(fixture_path))
    assert pages, "Expected PDF to load pages"
    text = "\n".join([p[1] for p in pages]).strip()
    assert "Hello PDF" in text


@pytest.mark.anyio
async def test_pdf_chunks_include_page_number_and_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"
    pipeline, captured = _build_pipeline()
    bm25_captured = _capture_bm25(monkeypatch)

    def _fake_platinum_extraction(*, text: str, filename: str):
        return SimpleNamespace(manufacturer="SealAI", product_name=filename, operating_points=[], safety_exclusions=[])

    def _fake_process_document_pipeline(_llm_output, _doc_id, _additional_metadata):
        return SimpleNamespace(
            status=SimpleNamespace(value="published"),
            extracted_points=[
                {
                    "vector_text": "Hello PDF",
                    "source_type": "pdf",
                    "source_url": str(fixture_path),
                    "page_number": 1,
                    "additional_metadata": {},
                }
            ],
            quarantine_report=[],
        )

    monkeypatch.setattr(rag_ingest, "_extract_platinum_structured_llm", _fake_platinum_extraction)
    monkeypatch.setattr(rag_ingest, "process_document_pipeline", _fake_process_document_pipeline)

    pipeline.process_document(
        str(fixture_path),
        tenant_id="tenant-1",
        document_id="doc-1",
        visibility="public",
        category="datasheet",
        route_key="material_datasheet",
        tags=["material", "compound"],
        source_system="paperless",
        source_document_id="11",
        source_modified_at=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
    )

    points = captured.get("points") or []
    assert points, "Expected PDF to produce at least one chunk"
    point = points[0]
    payload = getattr(point, "payload", None) or {}
    metadata = payload.get("metadata") or {}
    assert metadata.get("page_number") == 1
    assert metadata.get("tenant_id") == "tenant-1"
    assert metadata.get("category") == "datasheet"
    assert metadata.get("route_key") == "material_datasheet"
    assert metadata.get("tags") == ["material", "compound"]
    assert metadata.get("source_system") == "paperless"
    assert metadata.get("source_document_id") == "11"
    assert metadata.get("source_modified_at") == "2026-03-12T10:00:00+00:00"
    assert payload.get("tenant_id") == "tenant-1"
    bm25_docs = bm25_captured.get("docs") or []
    assert bm25_docs, "Expected BM25 upsert to receive documents"
    bm25_meta = bm25_docs[0].metadata
    assert bm25_meta.get("route_key") == "material_datasheet"
    assert bm25_meta.get("tags") == ["material", "compound"]
    assert bm25_meta.get("category") == "datasheet"
    assert bm25_meta.get("source_system") == "paperless"
    assert bm25_meta.get("source_document_id") == "11"
    assert bm25_meta.get("source_modified_at") == "2026-03-12T10:00:00+00:00"


@pytest.mark.anyio
@pytest.mark.parametrize("route_key", ["standard_or_norm", "technical_knowledge", "general_technical_doc"])
async def test_pdf_generic_routes_skip_specialized_etl(
    monkeypatch: pytest.MonkeyPatch,
    route_key: str,
) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"
    pipeline, captured = _build_pipeline()
    _capture_bm25(monkeypatch)

    def _unexpected_platinum(*args, **kwargs):
        raise AssertionError("specialized PDF ETL must not run for generic routes")

    monkeypatch.setattr(rag_ingest, "_extract_platinum_structured_llm", _unexpected_platinum)

    stats = pipeline.process_document(
        str(fixture_path),
        tenant_id="tenant-1",
        document_id=f"doc-{route_key}",
        visibility="public",
        route_key=route_key,
    )

    points = captured.get("points") or []
    assert stats.chunks > 0
    assert points, "Expected generic PDF ingestion to produce chunks"
    payload = getattr(points[0], "payload", None) or {}
    assert "document_meta" not in payload
    metadata = payload.get("metadata") or {}
    assert metadata.get("page_number") == 1
    assert metadata.get("route_key") == route_key


@pytest.mark.anyio
@pytest.mark.parametrize("route_key", ["material_datasheet", "product_datasheet"])
async def test_pdf_specialized_routes_keep_platinum_path(
    monkeypatch: pytest.MonkeyPatch,
    route_key: str,
) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"
    pipeline, captured = _build_pipeline()
    _capture_bm25(monkeypatch)
    specialized_calls = {"count": 0}

    def _fake_platinum_extraction(*, text: str, filename: str):
        specialized_calls["count"] += 1
        return SimpleNamespace(manufacturer="SealAI", product_name=filename, operating_points=[], safety_exclusions=[])

    def _fake_process_document_pipeline(_llm_output, _doc_id, _additional_metadata):
        return SimpleNamespace(
            status=SimpleNamespace(value="published"),
            extracted_points=[
                {
                    "vector_text": "Hello PDF",
                    "source_type": "pdf",
                    "source_url": str(fixture_path),
                    "page_number": 1,
                    "additional_metadata": {},
                }
            ],
            quarantine_report=[],
        )

    monkeypatch.setattr(rag_ingest, "_extract_platinum_structured_llm", _fake_platinum_extraction)
    monkeypatch.setattr(rag_ingest, "process_document_pipeline", _fake_process_document_pipeline)

    stats = pipeline.process_document(
        str(fixture_path),
        tenant_id="tenant-1",
        document_id=f"doc-{route_key}",
        visibility="public",
        route_key=route_key,
    )

    points = captured.get("points") or []
    assert stats.chunks == 1
    assert specialized_calls["count"] == 1
    assert points, "Expected specialized PDF ingestion to produce chunks"
    payload = getattr(points[0], "payload", None) or {}
    assert "document_meta" in payload
