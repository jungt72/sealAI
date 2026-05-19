from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import rag as rag_endpoint
from app.models.rag_document import RagDocument
from app.services.auth.dependencies import RequestUser
from app.services.rag.constants import RAG_SHARED_TENANT_ID


class DummyResult:
    def __init__(self, items: list[RagDocument]) -> None:
        self._items = items

    def scalars(self) -> "DummyResult":
        return self

    def all(self) -> list[RagDocument]:
        return list(self._items)


class DummySession:
    def __init__(self, docs: list[RagDocument]) -> None:
        self.docs = list(docs)
        self.execute_calls = 0
        self.add_calls = 0
        self.commit_calls = 0
        self.delete_calls = 0

    async def execute(self, stmt: Any) -> DummyResult:
        self.execute_calls += 1
        items = list(self.docs)
        filters: dict[str, Any] = {}
        enabled_not_false = False
        for criterion in getattr(stmt, "_where_criteria", []):
            left = getattr(criterion, "left", None)
            right = getattr(criterion, "right", None)
            operator = getattr(criterion, "operator", None)
            name = getattr(left, "name", None)
            value = getattr(right, "value", None)
            operator_name = getattr(operator, "__name__", "")
            if name == "enabled" and "is_not" in operator_name:
                enabled_not_false = True
                continue
            if name:
                filters[name] = value
        for key, value in filters.items():
            items = [item for item in items if getattr(item, key, None) == value]
        if enabled_not_false:
            items = [item for item in items if getattr(item, "enabled", None) is not False]
        limit_clause = getattr(stmt, "_limit_clause", None)
        limit_value = getattr(limit_clause, "value", None)
        if isinstance(limit_value, int):
            items = items[:limit_value]
        return DummyResult(items)

    def add(self, _obj: object) -> None:
        self.add_calls += 1

    async def commit(self) -> None:
        self.commit_calls += 1

    async def delete(self, _obj: object) -> None:
        self.delete_calls += 1


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _admin() -> RequestUser:
    return RequestUser(user_id="admin-1", username="admin", sub="admin-1", roles=["rag_admin"])


def _user() -> RequestUser:
    return RequestUser(user_id="user-1", username="user", sub="user-1", roles=[])


def _doc(
    *,
    document_id: str = "rag-doc-1",
    source_id: str | None = "42",
    source_system: str = "paperless",
    route: str = "material_datasheet",
    filename: str | None = "FKM water orientation sheet.pdf",
    tags: list[str] | None = None,
    extracted_candidates: Any = None,
    tenant_id: str = RAG_SHARED_TENANT_ID,
    enabled: bool = True,
) -> RagDocument:
    return RagDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        status="indexed",
        visibility="public",
        enabled=enabled,
        filename=filename,
        content_type="application/pdf",
        size_bytes=123,
        category=route,
        route_key=route,
        tags=tags or [],
        sha256=f"sha256:{document_id}",
        path=f"/tmp/{document_id}.pdf",
        source_system=source_system,
        source_document_id=source_id,
        extraction_status="extracted" if extracted_candidates is not None else "not_extracted",
        extracted_candidates=extracted_candidates,
        evidence_refs=[],
        provenance="documented",
    )


def _valid_candidate(**extra: object) -> dict[str, object]:
    candidate: dict[str, object] = {
        "material": "FKM",
        "medium": "water",
        "temperature_min_c": 0,
        "temperature_max_c": 80,
        "text": "Evidence-backed precheck context for FKM and water.",
    }
    candidate.update(extra)
    return candidate


@pytest.mark.anyio
async def test_dry_run_endpoint_requires_rag_admin() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await rag_endpoint.material_evidence_dry_run(
            source_system="paperless",
            route=None,
            limit=25,
            include_invalid=True,
            current_user=_user(),
            session=DummySession([]),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_dry_run_endpoint_reads_paperless_docs_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_qdrant_call(**_kwargs: object) -> int:
        raise AssertionError("dry-run must not call Qdrant helpers")

    monkeypatch.setattr(rag_endpoint, "_qdrant_vector_count", _fail_qdrant_call)
    monkeypatch.setattr(rag_endpoint, "_qdrant_delete_document", _fail_qdrant_call)
    session = DummySession([_doc(extracted_candidates=[_valid_candidate()])])

    payload = await rag_endpoint.material_evidence_dry_run(
        source_system="paperless",
        route=None,
        limit=25,
        include_invalid=True,
        current_user=_admin(),
        session=session,
    )

    assert payload["read_only"] is True
    assert payload["valid_count"] == 1
    assert session.execute_calls == 1
    assert session.add_calls == 0
    assert session.commit_calls == 0
    assert session.delete_calls == 0


@pytest.mark.anyio
async def test_dry_run_maps_valid_material_datasheet_doc() -> None:
    session = DummySession([_doc(source_id="paperless-42", extracted_candidates=[_valid_candidate()])])

    payload = await rag_endpoint.material_evidence_dry_run(
        source_system="paperless",
        route="material_datasheet",
        limit=25,
        include_invalid=True,
        current_user=_admin(),
        session=session,
    )

    assert payload["valid_count"] == 1
    result = payload["results"][0]
    assert result["source_reference"] == "paperless:paperless-42"
    assert result["source_id"] == "paperless-42"
    assert result["card_candidate"]["final_approval_claim_allowed"] is False


@pytest.mark.anyio
async def test_dry_run_reports_invalid_missing_metadata() -> None:
    session = DummySession([_doc(document_id="rag-missing", source_id=None, filename=None, extracted_candidates=[])])

    payload = await rag_endpoint.material_evidence_dry_run(
        source_system="paperless",
        route=None,
        limit=25,
        include_invalid=True,
        current_user=_admin(),
        session=session,
    )

    assert payload["skipped_count"] == 1
    assert payload["grouped_missing_fields"]["source_title"] == 1
    assert payload["grouped_missing_fields"]["material_or_medium"] == 1


@pytest.mark.anyio
async def test_dry_run_downgrades_tags_only() -> None:
    session = DummySession(
        [
            _doc(
                document_id="rag-tags-only",
                source_id="tags-only",
                route="technical_knowledge",
                filename="FKM oil tag record.pdf",
                tags=["FKM", "oil"],
                extracted_candidates=[],
            )
        ]
    )

    payload = await rag_endpoint.material_evidence_dry_run(
        source_system="paperless",
        route="technical_knowledge",
        limit=25,
        include_invalid=True,
        current_user=_admin(),
        session=session,
    )

    assert payload["downgraded_count"] == 1
    assert payload["results"][0]["status"] == "downgraded"
    assert "tags_only_context" in payload["results"][0]["limitations"]


@pytest.mark.anyio
async def test_dry_run_does_not_return_full_raw_text() -> None:
    long_text = "A" * 2000
    session = DummySession([_doc(extracted_candidates=[_valid_candidate(text=long_text)])])

    payload = await rag_endpoint.material_evidence_dry_run(
        source_system="paperless",
        route=None,
        limit=25,
        include_invalid=True,
        current_user=_admin(),
        session=session,
    )

    serialized = str(payload)
    assert long_text not in serialized
    assert "A" * 600 not in serialized
    excerpt = payload["results"][0]["card_candidate"]["excerpt_short"]
    assert len(excerpt) <= 323


@pytest.mark.anyio
async def test_dry_run_limit_is_capped() -> None:
    docs = [
        _doc(document_id=f"rag-doc-{index}", source_id=str(index), extracted_candidates=[_valid_candidate()])
        for index in range(105)
    ]
    session = DummySession(docs)

    payload = await rag_endpoint.material_evidence_dry_run(
        source_system="paperless",
        route=None,
        limit=500,
        include_invalid=False,
        current_user=_admin(),
        session=session,
    )

    assert payload["limit"] == 100
    assert payload["total_considered"] == 100
    assert len(payload["results"]) == 100


@pytest.mark.anyio
async def test_dry_run_route_filter() -> None:
    session = DummySession(
        [
            _doc(document_id="rag-material", source_id="1", route="material_datasheet", extracted_candidates=[_valid_candidate()]),
            _doc(document_id="rag-knowledge", source_id="2", route="technical_knowledge", extracted_candidates=[_valid_candidate()]),
        ]
    )

    payload = await rag_endpoint.material_evidence_dry_run(
        source_system="paperless",
        route="technical_knowledge",
        limit=25,
        include_invalid=True,
        current_user=_admin(),
        session=session,
    )

    assert payload["total_considered"] == 1
    assert payload["results"][0]["route"] == "technical_knowledge"
