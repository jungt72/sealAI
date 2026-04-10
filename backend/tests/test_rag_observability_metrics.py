from __future__ import annotations

import sys
import types

from app.observability import metrics as metrics_mod


class _DummyCollectionInfo:
    points_count = 42
    indexed_vectors_count = 42


def _counter_value(counter, **labels) -> float:
    try:
        return counter.labels(**labels)._value.get()
    except Exception:
        return 0.0


def test_refresh_qdrant_collection_metrics_updates_gauges(monkeypatch) -> None:
    class _DummyClient:
        def __init__(self, **_kwargs):
            pass

        def get_collection(self, collection: str):
            assert collection == "sealai_technical_docs"
            return _DummyCollectionInfo()

    monkeypatch.setattr(metrics_mod, "_default_qdrant_collection", lambda: "sealai_technical_docs")
    monkeypatch.setattr(metrics_mod, "_default_qdrant_url", lambda: "http://qdrant:6333")
    qdrant_stub = types.ModuleType("qdrant_client")
    qdrant_stub.QdrantClient = _DummyClient
    monkeypatch.setitem(sys.modules, "qdrant_client", qdrant_stub)

    metrics_mod.refresh_qdrant_collection_metrics(force=True)

    assert metrics_mod.QDRANT_COLLECTION_STATUS.labels(collection="sealai_technical_docs")._value.get() == 1
    assert metrics_mod.QDRANT_COLLECTION_POINTS.labels(collection="sealai_technical_docs")._value.get() == 42
    assert metrics_mod.QDRANT_COLLECTION_INDEXED_VECTORS.labels(collection="sealai_technical_docs")._value.get() == 42


def test_track_rag_ingest_records_success_and_timestamp(monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(metrics_mod, "refresh_qdrant_collection_metrics", lambda force=False, collection=None: calls.append(bool(force)))

    before = _counter_value(metrics_mod.RAG_INGEST_DOCUMENTS_TOTAL, source="paperless", status="indexed")
    metrics_mod.track_rag_ingest("paperless", "indexed", 0.25)
    after = _counter_value(metrics_mod.RAG_INGEST_DOCUMENTS_TOTAL, source="paperless", status="indexed")

    assert after == before + 1
    assert metrics_mod.RAG_LAST_SUCCESSFUL_INGEST_TIMESTAMP_SECONDS.labels(source="paperless")._value.get() > 0
    assert calls and calls[-1] is True


def test_track_rag_sync_records_last_run_counts(monkeypatch) -> None:
    monkeypatch.setattr(metrics_mod, "refresh_qdrant_collection_metrics", lambda force=False, collection=None: None)

    before = _counter_value(metrics_mod.RAG_SYNC_RUNS_TOTAL, source="paperless", status="success")
    metrics_mod.track_rag_sync(
        "paperless",
        "success",
        {
            "scanned": 10,
            "queued": 3,
            "skipped": 6,
            "errors": 1,
            "ingest_ready": 8,
            "pilot_ready": 7,
            "missing_pilot_tags": 3,
        },
    )
    after = _counter_value(metrics_mod.RAG_SYNC_RUNS_TOTAL, source="paperless", status="success")

    assert after == before + 1
    assert metrics_mod.RAG_SYNC_LAST_DOCUMENTS.labels(source="paperless", result="queued")._value.get() == 3
    assert metrics_mod.RAG_SYNC_LAST_DOCUMENTS.labels(source="paperless", result="errors")._value.get() == 1
