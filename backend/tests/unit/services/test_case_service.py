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

    def scalars(self) -> "_Result":
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


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
                    "application_pattern_id": row.application_pattern_id,
                    "calc_library_version": row.calc_library_version,
                    "case_revision": row.case_revision,
                    "engineering_path": row.engineering_path,
                    "inquiry_admissible": row.inquiry_admissible,
                    "payload": row.payload,
                    "phase": row.phase,
                    "pre_gate_classification": row.pre_gate_classification,
                    "request_type": row.request_type,
                    "rfq_ready": row.rfq_ready,
                    "risk_engine_version": row.risk_engine_version,
                    "ruleset_version": row.ruleset_version,
                    "schema_version": row.schema_version,
                    "sealing_material_family": row.sealing_material_family,
                    "session_id": row.session_id,
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
                if field_name == "tenant_id" and value is None:
                    case_row.__dict__["tenant_id"] = None
                else:
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
    case_number: str | None = None,
    user_id: str = "user-1",
) -> str:
    case_id = str(uuid.uuid4())
    case_row = CaseRecord(
        id=case_id,
        case_number=case_number or f"CASE-{case_id[:8]}",
        user_id=user_id,
        tenant_id=tenant_id if tenant_id is not None else "tenant-1",
        case_revision=case_revision,
        status="active",
        payload={},
    )
    if tenant_id is None:
        case_row.__dict__["tenant_id"] = None
    session.store.cases.append(case_row)
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


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_case_record_rejects_missing_tenant_id(tenant_id: object) -> None:
    with pytest.raises(ValueError, match="tenant_id is required"):
        CaseRecord(
            case_number="CASE-MODEL-TENANT",
            user_id="user-1",
            tenant_id=tenant_id,
            case_revision=0,
            payload={},
        )


@pytest.mark.parametrize(
    ("case_revision", "message"),
    [
        (-1, "case_revision must be non-negative"),
        ("0", "case_revision must be an integer"),
        (False, "case_revision must be an integer"),
    ],
)
def test_case_record_rejects_invalid_case_revision(
    case_revision: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CaseRecord(
            case_number="CASE-MODEL-REVISION",
            user_id="user-1",
            tenant_id="tenant-1",
            case_revision=case_revision,
            payload={},
        )


def test_case_record_payload_must_be_dict() -> None:
    with pytest.raises(ValueError, match="payload must be a dict"):
        CaseRecord(
            case_number="CASE-MODEL-PAYLOAD",
            user_id="user-1",
            tenant_id="tenant-1",
            case_revision=0,
            payload=["not", "a", "dict"],
        )


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
async def test_create_case_applies_readiness_case_updates(
    session: _FakeAsyncSession,
) -> None:
    case_row = await CaseService(session).create_case(
        case_number="CASE-CREATE-READINESS",
        user_id="user-1",
        tenant_id="tenant-1",
        actor="test",
        state_json={"created": True},
        case_updates={"inquiry_admissible": True, "rfq_ready": True},
    )

    assert case_row.inquiry_admissible is True
    assert case_row.rfq_ready is True


@pytest.mark.asyncio
@pytest.mark.parametrize("field_name", ["case_number", "tenant_id", "user_id"])
async def test_create_case_rejects_identity_case_updates(
    session: _FakeAsyncSession,
    field_name: str,
) -> None:
    with pytest.raises(
        InvalidMutationError,
        match=f"{field_name} cannot be changed through case_updates",
    ):
        await CaseService(session).create_case(
            case_number="CASE-CREATE-IDENTITY",
            user_id="user-1",
            tenant_id="tenant-1",
            actor="test",
            case_updates={field_name: "changed"},
        )

    assert len(session.store.cases) == 0
    assert len(session.store.events) == 0
    assert len(session.store.snapshots) == 0
    assert len(session.store.outbox) == 0


@pytest.mark.asyncio
async def test_create_case_rejects_non_dict_state_json(
    session: _FakeAsyncSession,
) -> None:
    with pytest.raises(InvalidMutationError, match="state_json must be a dict"):
        await CaseService(session).create_case(
            case_number="CASE-CREATE-BAD-STATE",
            user_id="user-1",
            tenant_id="tenant-1",
            actor="test",
            state_json=["not", "a", "dict"],  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_create_case_rejects_non_dict_case_updates(
    session: _FakeAsyncSession,
) -> None:
    with pytest.raises(InvalidMutationError, match="case_updates must be a dict"):
        await CaseService(session).create_case(
            case_number="CASE-CREATE-BAD-UPDATES",
            user_id="user-1",
            tenant_id="tenant-1",
            actor="test",
            case_updates=[],  # type: ignore[arg-type]
        )


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
async def test_apply_mutation_persists_false_readiness_case_updates(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)
    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    case_row.inquiry_admissible = True
    case_row.rfq_ready = True

    await CaseService(session).apply_mutation(
        case_id=case_id,
        expected_revision=0,
        event_type=MutationEventType.FIELD_UPDATED,
        payload=_payload(inquiry_admissible=False, rfq_ready=False),
        actor="user-1",
        actor_type=ActorType.USER,
    )

    assert case_row.inquiry_admissible is False
    assert case_row.rfq_ready is False


@pytest.mark.asyncio
@pytest.mark.parametrize("field_name", ["case_number", "tenant_id", "user_id"])
async def test_apply_mutation_rejects_identity_case_updates_without_side_effects(
    session: _FakeAsyncSession,
    field_name: str,
) -> None:
    case_id = await _insert_case(session)

    with pytest.raises(
        InvalidMutationError,
        match=f"{field_name} cannot be changed through case_updates",
    ):
        await CaseService(session).apply_mutation(
            case_id=case_id,
            expected_revision=0,
            event_type=MutationEventType.FIELD_UPDATED,
            payload=_payload(**{field_name: "changed"}),
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
async def test_apply_mutation_rejects_none_case_update_without_side_effects(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)

    with pytest.raises(
        InvalidMutationError,
        match="payload.case_updates.status cannot be None",
    ):
        await CaseService(session).apply_mutation(
            case_id=case_id,
            expected_revision=0,
            event_type=MutationEventType.FIELD_UPDATED,
            payload=_payload(status=None),
            actor="user-1",
            actor_type=ActorType.USER,
        )

    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    assert case_row.status == "active"
    assert case_row.case_revision == 0
    assert len(session.store.events) == 0
    assert len(session.store.snapshots) == 0
    assert len(session.store.outbox) == 0


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
async def test_write_snapshot_rejects_non_dict_case_updates(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)

    with pytest.raises(InvalidMutationError, match="case_updates must be a dict"):
        await CaseService(session).write_snapshot(
            case_id=case_id,
            state_json={"field": "value"},
            actor="user-1",
            actor_type=ActorType.USER,
            case_updates=[],  # type: ignore[arg-type]
        )

    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    assert case_row.case_revision == 0
    assert len(session.store.events) == 0
    assert len(session.store.snapshots) == 0
    assert len(session.store.outbox) == 0


@pytest.mark.asyncio
async def test_write_snapshot_does_not_dedupe_nonempty_case_updates(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)
    session.store.snapshots.append(
        CaseStateSnapshot(
            case_id=case_id,
            revision=0,
            state_json={"field": "value"},
            basis_hash="basis-1",
        )
    )

    snapshot = await CaseService(session).write_snapshot(
        case_id=case_id,
        state_json={"field": "value"},
        basis_hash="basis-1",
        actor="user-1",
        actor_type=ActorType.USER,
        case_updates={"status": "qualified"},
    )

    case_row = await session.get(CaseRecord, case_id)
    assert case_row is not None
    assert case_row.status == "qualified"
    assert case_row.case_revision == 1
    assert snapshot.revision == 1
    assert len(session.store.events) == 1
    assert len(session.store.outbox) == 1


@pytest.mark.asyncio
async def test_get_latest_snapshot_for_case_number_reads_newest_revision(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session, case_number="CASE-READ-1")
    session.store.snapshots.extend(
        [
            CaseStateSnapshot(
                case_id=case_id,
                revision=1,
                state_json={"revision": 1},
                basis_hash="basis-1",
            ),
            CaseStateSnapshot(
                case_id=case_id,
                revision=2,
                state_json={"revision": 2},
                basis_hash="basis-2",
            ),
        ]
    )

    result = await CaseService(session).get_latest_snapshot_for_case_number(
        case_number="CASE-READ-1",
        user_id="user-1",
    )

    assert result is not None
    case_row, snapshot_row = result
    assert case_row.id == case_id
    assert snapshot_row.revision == 2
    assert snapshot_row.state_json == {"revision": 2}


@pytest.mark.asyncio
async def test_get_snapshot_by_revision_for_case_number_uses_target_revision(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session, case_number="CASE-READ-2")
    session.store.snapshots.extend(
        [
            CaseStateSnapshot(case_id=case_id, revision=1, state_json={"revision": 1}),
            CaseStateSnapshot(case_id=case_id, revision=2, state_json={"revision": 2}),
        ]
    )

    result = await CaseService(session).get_snapshot_by_revision_for_case_number(
        case_number="CASE-READ-2",
        revision=1,
        user_id="user-1",
    )

    assert result is not None
    _, snapshot_row = result
    assert snapshot_row.revision == 1
    assert snapshot_row.state_json == {"revision": 1}


@pytest.mark.asyncio
async def test_snapshot_reads_require_matching_owner_guard(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(
        session,
        case_number="CASE-READ-3",
        user_id="owner-1",
    )
    session.store.snapshots.append(
        CaseStateSnapshot(case_id=case_id, revision=1, state_json={"revision": 1})
    )

    result = await CaseService(session).get_latest_snapshot_for_case_number(
        case_number="CASE-READ-3",
        user_id="owner-2",
    )

    assert result is None


@pytest.mark.asyncio
async def test_snapshot_read_rejects_missing_owner_guard(
    session: _FakeAsyncSession,
) -> None:
    with pytest.raises(InvalidMutationError, match="user_id is required"):
        await CaseService(session).get_latest_snapshot_for_case_number(
            case_number="CASE-READ-OWNER",
            user_id=None,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_snapshot_read_rejects_negative_revision(
    session: _FakeAsyncSession,
) -> None:
    with pytest.raises(InvalidMutationError, match="revision must be non-negative"):
        await CaseService(session).get_snapshot_by_revision_for_case_number(
            case_number="CASE-READ-NEGATIVE",
            revision=-1,
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_list_snapshot_revisions_for_case_number_reads_newest_first(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session, case_number="CASE-READ-4")
    session.store.snapshots.extend(
        [
            CaseStateSnapshot(case_id=case_id, revision=1, state_json={"revision": 1}),
            CaseStateSnapshot(case_id=case_id, revision=3, state_json={"revision": 3}),
            CaseStateSnapshot(case_id=case_id, revision=2, state_json={"revision": 2}),
        ]
    )

    items = await CaseService(session).list_snapshot_revisions_for_case_number(
        case_number="CASE-READ-4",
        user_id="user-1",
        limit=2,
    )

    assert [item.revision for item in items] == [3, 2]


@pytest.mark.asyncio
async def test_list_snapshot_revisions_rejects_missing_owner_guard(
    session: _FakeAsyncSession,
) -> None:
    with pytest.raises(InvalidMutationError, match="user_id is required"):
        await CaseService(session).list_snapshot_revisions_for_case_number(
            case_number="CASE-READ-LIST-OWNER",
            user_id=None,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_list_snapshot_revisions_rejects_non_positive_limit(
    session: _FakeAsyncSession,
) -> None:
    with pytest.raises(InvalidMutationError, match="limit must be positive"):
        await CaseService(session).list_snapshot_revisions_for_case_number(
            case_number="CASE-READ-LIST-LIMIT",
            user_id="user-1",
            limit=0,
        )


@pytest.mark.asyncio
async def test_get_latest_snapshot_revision_for_case_id_returns_newest_revision(
    session: _FakeAsyncSession,
) -> None:
    case_id = await _insert_case(session)
    session.store.snapshots.extend(
        [
            CaseStateSnapshot(case_id=case_id, revision=1, state_json={"revision": 1}),
            CaseStateSnapshot(case_id=case_id, revision=4, state_json={"revision": 4}),
        ]
    )

    revision = await CaseService(session).get_latest_snapshot_revision_for_case_id(case_id)

    assert revision == 4


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
