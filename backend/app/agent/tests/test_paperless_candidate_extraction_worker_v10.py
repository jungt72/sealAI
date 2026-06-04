from __future__ import annotations

from typing import Any

import pytest

from app.models.rag_document import RagDocument
from app.services.jobs import worker
from app.services.rag.constants import RAG_SHARED_TENANT_ID


class DummySession:
    def __init__(self) -> None:
        self.add_calls = 0
        self.commit_calls = 0

    def add(self, _obj: object) -> None:
        self.add_calls += 1

    async def commit(self) -> None:
        self.commit_calls += 1


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _doc(*, path: str, source_system: str = "paperless") -> RagDocument:
    return RagDocument(
        document_id="rag-doc-worker",
        tenant_id=RAG_SHARED_TENANT_ID,
        status="queued",
        visibility="public",
        enabled=True,
        filename="FKM water evidence.md",
        content_type="text/markdown",
        size_bytes=None,
        category="material_datasheet",
        route_key="material_datasheet",
        tags=["STS-MAT-FKM-A1"],
        sha256="sha256-worker",
        path=path,
        source_system=source_system,
        source_document_id="42",
        extraction_status="candidate_extraction_pending",
        extracted_candidates=[],
        evidence_refs=[],
        provenance="documented",
    )


@pytest.mark.anyio
async def test_worker_persists_paperless_extracted_candidates_after_indexing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    source = tmp_path / "source.md"
    source.write_text("FKM water evidence", encoding="utf-8")
    doc = _doc(path=str(source))
    session = DummySession()
    ingest_calls: list[dict[str, object]] = []
    candidate = {
        "document_id": doc.document_id,
        "material": "FKM",
        "medium": "water",
        "temperature_min_c": 0,
        "temperature_max_c": 80,
        "text": "Indexed candidate text.",
        "metadata": {
            "document_id": doc.document_id,
            "snippet_source": "qdrant_payload",
        },
    }

    def _ingest(_path: str, **kwargs: object) -> None:
        ingest_calls.append(dict(kwargs))

    def _load_candidates(
        docs: list[RagDocument], **kwargs: object
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        assert docs == [doc]
        assert kwargs["tenant_id"] == RAG_SHARED_TENANT_ID
        return [candidate], {
            "enabled": True,
            "status": "loaded",
            "loaded_candidate_count": 1,
        }

    monkeypatch.setattr(
        "app.services.rag.material_evidence_dry_run.load_material_evidence_indexed_snippet_raw_items",
        _load_candidates,
    )

    await worker.process_rag_document(
        session, doc, ingest_func=_ingest, use_thread=False
    )

    assert ingest_calls[0]["source_system"] == "paperless"
    assert doc.status == "indexed"
    assert doc.extraction_status == "candidate_extraction_ready"
    assert doc.extracted_candidates == [candidate]
    assert doc.ingest_stats["candidate_extraction"]["status"] == "loaded"
    assert doc.ingest_stats["candidate_extraction"]["loaded_candidate_count"] == 1
    assert session.add_calls >= 2
    assert session.commit_calls >= 2


@pytest.mark.anyio
async def test_worker_skips_candidate_extraction_for_non_paperless_docs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    source = tmp_path / "source.md"
    source.write_text("manual upload", encoding="utf-8")
    doc = _doc(path=str(source), source_system="upload")
    session = DummySession()

    def _ingest(_path: str, **_kwargs: object) -> None:
        return None

    def _fail_loader(
        *_args: object, **_kwargs: object
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        raise AssertionError(
            "non-Paperless docs must not run Paperless candidate extraction"
        )

    monkeypatch.setattr(
        "app.services.rag.material_evidence_dry_run.load_material_evidence_indexed_snippet_raw_items",
        _fail_loader,
    )

    await worker.process_rag_document(
        session, doc, ingest_func=_ingest, use_thread=False
    )

    assert doc.status == "indexed"
    assert doc.extraction_status == "indexed"
    assert doc.extracted_candidates == []
    assert "candidate_extraction" not in doc.ingest_stats
