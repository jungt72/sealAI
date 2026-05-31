"""Patch 1 — cross-tenant IDOR regression coverage for persisted RWDR cases.

The persisted RWDR case repository (``DbRWDRCaseStateRepository``) must only
expose a case to the (tenant_id, user_id) that owns it. This mirrors the
established ownership policy in ``RfqPreviewService._load_owned_case`` (filter on
both tenant_id AND user_id, return not-found on a miss with no existence leak —
the stricter, safe default).

These tests run against a real in-memory SQLite database so the actual SQL
ownership filter in ``DbRWDRCaseStateRepository._require`` is exercised
end-to-end, not mocked. Endpoint-level forwarding/404 mapping is covered in
``app/api/tests/test_rfq_endpoint.py``.
"""

from __future__ import annotations

import contextlib

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.services.rwdr_mvp_brief import (
    RWDR_CASE_STATE_SCHEMA_VERSION,
    RWDR_EXTRACTION_VERSION,
    RWDR_RULE_VERSION,
    RWDRCaseStateNotFound,
    diff_db_persisted_rwdr_case_snapshots,
    evaluate_db_persisted_rwdr_case,
    export_db_persisted_rwdr_case_markdown,
    export_db_persisted_rwdr_case_pdf_document,
    generate_db_persisted_rwdr_brief,
    get_db_persisted_rwdr_case,
    get_db_persisted_rwdr_case_snapshot,
    list_db_persisted_rwdr_case_snapshots,
    update_db_persisted_rwdr_confirmations,
)


_TABLES = (CaseRecord.__table__, CaseStateSnapshot.__table__)


@contextlib.contextmanager
def _sqlite_compatible_server_defaults():
    """Temporarily drop Postgres-only server defaults (e.g. ``'{}'::jsonb``).

    These dialect-specific defaults are emitted verbatim by ``create_all`` and
    are rejected by SQLite. They only matter for INSERTs that omit the column;
    the tests always provide explicit values, so dropping them for DDL is safe.
    The originals are restored afterwards to avoid leaking global model state.
    """
    saved: list[tuple[object, object]] = []
    for table in _TABLES:
        for column in table.columns:
            default = column.server_default
            if default is not None and "::" in str(getattr(default, "arg", "")):
                saved.append((column, default))
                column.server_default = None
    try:
        yield
    finally:
        for column, default in saved:
            column.server_default = default


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with _sqlite_compatible_server_defaults():
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(sync_conn, tables=list(_TABLES))
            )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _seed_payload() -> dict[str, object]:
    return {
        "schema_version": RWDR_CASE_STATE_SCHEMA_VERSION,
        "raw_inquiry_text": "Wellendichtring 45x62x8, Öl, 1500 U/min.",
        "evidence_fields": [],
        "extraction_version": RWDR_EXTRACTION_VERSION,
        "rule_version": RWDR_RULE_VERSION,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "created_by": "user-1",
    }


async def _seed_owned_case(
    session: AsyncSession,
    *,
    case_id: str = "case-1",
    tenant_id: str = "tenant-1",
    user_id: str = "user-1",
) -> str:
    """Persist an RWDR case + two snapshots owned by (tenant_id, user_id)."""
    session.add(
        CaseRecord(
            id=case_id,
            case_number=f"RWDR-{case_id[:8].upper()}",
            user_id=user_id,
            tenant_id=tenant_id,
            status="active",
            request_type="rwdr_rfq",
            engineering_path="rwdr",
            schema_version=RWDR_CASE_STATE_SCHEMA_VERSION,
            ruleset_version=RWDR_RULE_VERSION,
            payload=_seed_payload(),
        )
    )
    for revision in (1, 2):
        session.add(
            CaseStateSnapshot(
                id=f"{case_id}-snap-{revision}",
                case_id=case_id,
                revision=revision,
                state_json={
                    "snapshot_id": f"{case_id}-snap-{revision}",
                    "case_id": case_id,
                    "revision_number": revision,
                    "event_type": "case_created_after_analyze",
                    "snapshot_payload": _seed_payload(),
                    "deterministic_payload_json": {},
                },
                basis_hash="hash",
                ontology_version=RWDR_CASE_STATE_SCHEMA_VERSION,
                prompt_version=RWDR_EXTRACTION_VERSION,
                model_version=RWDR_RULE_VERSION,
            )
        )
    await session.commit()
    return case_id


def _guarded_repository_calls(
    session: AsyncSession, case_id: str, *, tenant_id: str, user_id: str
) -> dict[str, object]:
    """Every persisted-case repository entry point behind the ownership guard."""
    scope = {"tenant_id": tenant_id, "user_id": user_id}
    return {
        "get": get_db_persisted_rwdr_case(session=session, case_id=case_id, **scope),
        "confirm": update_db_persisted_rwdr_confirmations(
            session=session,
            case_id=case_id,
            decisions=[
                {"field": "shaft_diameter_d1_mm", "action": "edit", "value": "45", "unit": "mm"}
            ],
            **scope,
        ),
        "evaluate": evaluate_db_persisted_rwdr_case(session=session, case_id=case_id, **scope),
        "brief": generate_db_persisted_rwdr_brief(session=session, case_id=case_id, **scope),
        "export_md": export_db_persisted_rwdr_case_markdown(session=session, case_id=case_id, **scope),
        "export_pdf": export_db_persisted_rwdr_case_pdf_document(session=session, case_id=case_id, **scope),
        "list_snapshots": list_db_persisted_rwdr_case_snapshots(session=session, case_id=case_id, **scope),
        "get_snapshot": get_db_persisted_rwdr_case_snapshot(
            session=session, case_id=case_id, revision_number=1, **scope
        ),
        "diff_snapshots": diff_db_persisted_rwdr_case_snapshots(
            session=session, case_id=case_id, from_revision=1, to_revision=2, **scope
        ),
    }


@pytest.mark.asyncio
async def test_owner_can_use_all_guarded_paths(async_session: AsyncSession) -> None:
    # Regression: the ownership guard must not block the legitimate owner from
    # any guarded read/mutate/export/snapshot method.
    case_id = await _seed_owned_case(async_session)

    blocked: list[str] = []
    results: dict[str, object] = {}
    for name, coro in _guarded_repository_calls(
        async_session, case_id, tenant_id="tenant-1", user_id="user-1"
    ).items():
        try:
            results[name] = await coro
        except RWDRCaseStateNotFound:
            blocked.append(name)
    assert not blocked, f"owner unexpectedly blocked from: {blocked}"
    assert results["get"]["case_id"] == case_id
    assert results["list_snapshots"]
    assert results["get_snapshot"]["revision_number"] == 1


@pytest.mark.asyncio
async def test_get_persisted_case_foreign_tenant_not_found(async_session: AsyncSession) -> None:
    case_id = await _seed_owned_case(async_session)

    with pytest.raises(RWDRCaseStateNotFound):
        await get_db_persisted_rwdr_case(
            session=async_session, case_id=case_id, tenant_id="tenant-2", user_id="user-2"
        )


@pytest.mark.asyncio
async def test_get_persisted_case_cross_user_same_tenant_not_found(
    async_session: AsyncSession,
) -> None:
    # Owner-only policy: a same-tenant non-owner must not reach the case.
    case_id = await _seed_owned_case(async_session)

    with pytest.raises(RWDRCaseStateNotFound):
        await get_db_persisted_rwdr_case(
            session=async_session, case_id=case_id, tenant_id="tenant-1", user_id="user-2"
        )


@pytest.mark.asyncio
async def test_all_guarded_paths_reject_foreign_tenant(async_session: AsyncSession) -> None:
    case_id = await _seed_owned_case(async_session)

    leaked: list[str] = []
    for name, coro in _guarded_repository_calls(
        async_session, case_id, tenant_id="tenant-2", user_id="user-2"
    ).items():
        try:
            await coro
        except RWDRCaseStateNotFound:
            continue
        leaked.append(name)
    assert not leaked, f"foreign tenant reached guarded paths: {leaked}"


@pytest.mark.asyncio
async def test_all_guarded_paths_reject_cross_user_same_tenant(
    async_session: AsyncSession,
) -> None:
    case_id = await _seed_owned_case(async_session)

    leaked: list[str] = []
    for name, coro in _guarded_repository_calls(
        async_session, case_id, tenant_id="tenant-1", user_id="user-2"
    ).items():
        try:
            await coro
        except RWDRCaseStateNotFound:
            continue
        leaked.append(name)
    assert not leaked, f"same-tenant non-owner reached guarded paths: {leaked}"
