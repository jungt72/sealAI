from __future__ import annotations

import sys
import types
from pathlib import Path

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

    models_mod.PointStruct = _PointStruct
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


class _DenseVec:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class _DenseEmbedder:
    def embed(self, texts):
        return [_DenseVec([0.0, 0.0, 0.0]) for _ in texts]


@pytest.mark.anyio
async def test_pdf_extracts_text_non_empty() -> None:
    pytest.importorskip("pypdf")
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"
    pages = rag_ingest._load_pages(str(fixture_path))
    assert pages, "Expected PDF to load pages"
    text = "\n".join([p[1] for p in pages]).strip()
    assert "Hello PDF" in text


@pytest.mark.anyio
async def test_pdf_chunks_include_page_number_and_tenant() -> None:
    pytest.importorskip("pypdf")
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"

    pipeline = rag_ingest.IngestPipeline()
    pipeline._load_embedders = lambda: None
    pipeline._dense_embedder = _DenseEmbedder()

    captured = {}

    class _DummyClient:
        def upsert(self, _collection, points):
            captured["points"] = points

    pipeline.client = _DummyClient()

    pipeline.process_document(
        str(fixture_path),
        tenant_id="tenant-1",
        document_id="doc-1",
        visibility="public",
    )

    points = captured.get("points") or []
    assert points, "Expected PDF to produce at least one chunk"
    point = points[0]
    payload = getattr(point, "payload", None) or {}
    metadata = payload.get("metadata") or {}
    assert metadata.get("page_number") == 1
    assert metadata.get("tenant_id") == "tenant-1"
    assert payload.get("tenant_id") == "tenant-1"
