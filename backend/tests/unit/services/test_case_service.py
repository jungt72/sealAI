from __future__ import annotations

import pathlib
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy.sql.elements import BindParameter

from app.domain.mutation_events import ActorType, MutationEventType
from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.models.mutation_event_model import MutationEventModel
from app.models.outbox_model import OutboxModel
from app.services.case_service import (
    CaseService,
    InvalidMutationError,
    OptimisticLockError,
)


@pytest.fixture
def session() -> "_FakeAsyncSession":
    return _FakeAsyncSession()


@dataclass
class _Store:
    cases: list[CaseRecord] = field(default_factory=list)
    events: list[MutationEventModel] = field(default_factory=list)
    snapshots: list[CaseStateSnapshot] = field(default_factory=list)
    outbox: list[OutboxModel] = field(default_factory=list)


class _Result:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        if len(self._rows) != 1:
            raise AssertionError(f"expected one row, got {len(self._rows)}")
        return self._rows[0]


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.store = _Store()
        self._pending: list[Any] = []
        self._case_originals: dict[str, dict[str, Any]] = {}

    async def execute(self, query: Any) -> _Result:
        entity = query.column_descriptions[0].get("entity")
        if entity is CaseRecord:
            rows = list(self.store.cases)
        elif entity is CaseStateSnapshot:
            rows = list(self.store.snapshots)
        else:
            raise AssertionError(f"unexpected query entity: {entity!r}")

        for criterion in getattr(query, "_where_criteria", ()):
            field_name = criterion.left.name
            expected = criterion.right.value
            if isinstance(expected, BindParameter):
                expected = expected.value
            rows = [row for row in rows if getattr(row, field_name) == expected]

        if entity is CaseStateSnapshot:
            rows = sorted(rows, key=lambda row: int(row.revision), reverse=True)
        limit_clause = getattr(query, "_limit_clause", None)
        if limit_clause is not None:
            rows = rows[: int(limit_clause.value)]

        for row in rows:
            if isinstance(row, CaseRecord) and row.id not in self._case_originals:
                self._case_originals[row.id] = {
                    "case_revision": row.case_revision,
                    "status": row.status,
                    "subsegment": row.subsegment,
                    "tenant_id": row.tenant_id,
                    "user_id": row.user_id,
                }
        return _Result(rows)

    def add(self, instance: object) -> None:
        self._pending.append(instance)

    async def commit(self) -> None:
        for instance in self._pending:
            if isinstance(instance, CaseRecord):
                if instance.id is None:
                    instance.id = str(uuid.uuid4())
                self.store.cases.append(instance)
            elif isinstance(instance, MutationEventModel):
                self.store.events.append(instance)
            elif isinstance(instance, CaseStateSnapshot):
                self.store.snapshots.append(instance)
            elif isinstance(instance, OutboxModel):
                self.store.outbox.append(instance)
            else:
                raise AssertionError(f"unexpected pending instance: {type(instance)!r}")
        self._pending.clear()
        self._case_originals.clear()

    async def rollback(self) -> None:
        self._pending.clear()
        for case_id, original in self._case_originals.items():
            case_row = next(row for row in self.store.cases if row.id == case_id)
            for field_name, value in original.items():
                setattr(case_row, field_name, value)
        self._case_originals.clear()

    async def refresh(self, _instance: object) -> None:
        return None

    async def flush(self) -> None:
        for instance in self._pending:
            if isinstance(instance, CaseRecord) and instance.id is None:
                instance.id = str(uuid.uuid4())

    async def get(self, entity: type[Any], key: str) -> Any | None:
        if entity is CaseRecord:
            return next((row for row in self.store.cases if row.id == key), None)
        raise AssertionError(f"unexpected get entity: {entity!r}")


async def _insert_case(
    session: _FakeAsyncSession,
    *,
    case_revision: int = 0,
    tenant_id: str | None = "tenant-1",
) -> str:
    case_id = str(uuid.uuid4())
    session.store.cases.append(
        CaseRecord(
            id=case_id,
            case_number=f"CASE-{case_id[:8]}",
            user_id="user-1",
            tenant_id=tenant_id,
            case_revision=case_revision,
            status="active",
            payload={},
        )
    )
    return case_id


def _payload(**case_updates: Any) -> dict[str, Any]:
    return {
        "case_updates": case_updates,
        "snapshot": {
            "state_json": {"field": "value"},
            "basis_hash": "basis-1",
            "ontology_version": "sealai_norm_v1",
            "prompt_version": "prompt-v1",
            "model_version": "model-v1",
        },
    }


@pytest.mark.asyncio
async def test_create_case_with_valid_tenant_id_succeeds(
    session: _FakeAsyncSession,
) -> None:
    case_row = await CaseService(session).create_case(
        case_number="CASE-CREATE-1",
        user_id="user-1",
        tenant_id="tenant-1",
        actor="test",
        state_json={"created": True},
    )

    assert case_row.tenant_id == "tenant-1"
    assert case_row.case_revision == 1
    assert len(session.store.cases) == 1
    assert len(session.store.events) == 1
    assert len(session.store.snapshots) == 1
    assert len(session.store.outbox) == 1
    assert session.store.events[0].tenant_id == "tenant-1"
    assert session.store.outbox[0].tenant_id == "tenant-1"


@pytest.mark.asyncio
async def test_create_case_with_none_tenant_id_raises_invalid_mutation_error(
    session: _FakeAsyncSession,
) -> None:
    with pytest.raises(InvalidMutationError, match="tenant_id is required"):
        await CaseService(session).create_case(
            case_number="CASE-CREATE-2",
            user_id="user-1",
            tenant_id=None,  # type: ignore[arg-type]
            actor="test",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_id", ["", "   "])
async def test_create_case_with_blank_tenant_id_raises_invalid_mutation_error(
    session: _FakeAsyncSession,
    tenant_id: str,
) -> None:
    with pytest.raises(InvalidMutationError, match="tenant_id is required"):
        await CaseService(session).create_case(
            case_number="CASE-CREATE-3",
            user_id="user-1",
            tenant_id=tenant_id,
            actor="test",
        )


@pytest.mark.asyncio
async def test_apply_mutation_on_case_without_tenant_id_raises_invalid_mutation_error(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session, tenant_id=None)

    with pytest.raises(InvalidMutationError, match="tenant_id is required"):
        await CaseService(session).apply_mutation(
            case_id=case_id,
            expected_revision=0,
            event_type=MutationEventType.FIELD_UPDATED,
            payload=_payload(status="qualified"),
            actor="user-1",
            actor_type=ActorType.USER,
        )

    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    assert case_row.case_revision == 0
    assert len(session.store.events) == 0
    assert len(session.store.snapshots) == 0
    assert len(session.store.outbox) == 0


@pytest.mark.asyncio
async def test_apply_mutation_with_correct_expected_revision_succeeds(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)

    mutation = await CaseService(session).apply_mutation(
        case_id=case_id,
        expected_revision=0,
        event_type=MutationEventType.FIELD_UPDATED,
        payload=_payload(status="qualified"),
        actor="user-1",
        actor_type=ActorType.USER,
    )

    assert uuid.UUID(mutation.mutation_id)
    assert mutation.case_revision_before == 0
    assert mutation.case_revision_after == 1
    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    assert case_row.status == "qualified"


@pytest.mark.asyncio
async def test_wrong_revision_raises_optimistic_lock_error(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session, case_revision=1)

    with pytest.raises(OptimisticLockError):
        await CaseService(session).apply_mutation(
            case_id=case_id,
            expected_revision=0,
            event_type=MutationEventType.FIELD_UPDATED,
            payload=_payload(),
            actor="user-1",
            actor_type=ActorType.USER,
        )


@pytest.mark.asyncio
async def test_missing_case_raises_invalid_mutation_error(session: _FakeAsyncSession) -> None:
    with pytest.raises(InvalidMutationError):
        await CaseService(session).apply_mutation(
            case_id=str(uuid.uuid4()),
            expected_revision=0,
            event_type=MutationEventType.FIELD_UPDATED,
            payload=_payload(),
            actor="user-1",
            actor_type=ActorType.USER,
        )


@pytest.mark.asyncio
async def test_invalid_payload_raises_invalid_mutation_error(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)

    with pytest.raises(InvalidMutationError):
        await CaseService(session).apply_mutation(
            case_id=case_id,
            expected_revision=0,
            event_type=MutationEventType.FIELD_UPDATED,
            payload={"case_updates": {}},
            actor="user-1",
            actor_type=ActorType.USER,
        )


@pytest.mark.asyncio
async def test_case_revision_increases_exactly_by_one(session: _FakeAsyncSession) -> None:
    case_id = await _insert_case(session, case_revision=4)

    await CaseService(session).apply_mutation(
        case_id=case_id,
        expected_revision=4,
        event_type=MutationEventType.FIELD_UPDATED,
        payload=_payload(),
        actor="user-1",
        actor_type=ActorType.USER,
    )

    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    assert case_row.case_revision == 5


@pytest.mark.asyncio
async def test_successful_mutation_writes_one_event_snapshot_and_pending_outbox(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)

    await CaseService(session).apply_mutation(
        case_id=case_id,
        expected_revision=0,
        event_type=MutationEventType.FIELD_UPDATED,
        payload=_payload(),
        actor="user-1",
        actor_type=ActorType.USER,
    )

    assert len(session.store.events) == 1
    assert len(session.store.snapshots) == 1
    assert len(session.store.outbox) == 1

    event = session.store.events[0]
    snapshot = session.store.snapshots[0]
    outbox = session.store.outbox[0]

    assert event.event_type == "field_updated"
    assert event.tenant_id == "tenant-1"
    assert snapshot.revision == 1
    assert snapshot.state_json == {"field": "value"}
    assert outbox.status == "pending"
    assert outbox.mutation_id == event.mutation_id


@pytest.mark.asyncio
async def test_mid_transaction_failure_leaves_no_partial_writes(
    session: _FakeAsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = await _insert_case(session)
    service = CaseService(session)
    original_add = session.add
    seen_snapshot = False

    def fail_after_snapshot(instance: object, *_args: Any, **_kwargs: Any) -> None:
        nonlocal seen_snapshot
        if isinstance(instance, CaseStateSnapshot):
            seen_snapshot = True
        if seen_snapshot and isinstance(instance, OutboxModel):
            raise RuntimeError("synthetic mid-transaction failure")
        original_add(instance)

    monkeypatch.setattr(session, "add", fail_after_snapshot)

    with pytest.raises(RuntimeError):
        await service.apply_mutation(
            case_id=case_id,
            expected_revision=0,
            event_type=MutationEventType.FIELD_UPDATED,
            payload=_payload(status="qualified"),
            actor="user-1",
            actor_type=ActorType.USER,
        )

    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    assert case_row.case_revision == 0
    assert case_row.status == "active"
    assert len(session.store.events) == 0
    assert len(session.store.snapshots) == 0
    assert len(session.store.outbox) == 0


def test_case_service_has_no_agent_or_langgraph_imports() -> None:
    service_path = (
        pathlib.Path(__file__).parents[3] / "app" / "services" / "case_service.py"
    )
    source = service_path.read_text(encoding="utf-8")

    assert "langgraph" not in source
    assert "app.agent" not in source
