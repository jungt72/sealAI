from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.models.outbox_model import OutboxModel
from app.services.outbox_worker import OutboxWorker


@dataclass
class _ScalarResult:
    rows: list[OutboxModel]

    def all(self) -> list[OutboxModel]:
        return self.rows


@dataclass
class _Result:
    rows: list[OutboxModel]

    def scalars(self) -> _ScalarResult:
        return _ScalarResult(self.rows)


@dataclass
class _FakeSession:
    rows: list[OutboxModel] = field(default_factory=list)
    added: list[OutboxModel] = field(default_factory=list)
    commits: int = 0
    last_query: Any = None

    def execute(self, query: Any) -> _Result:
        self.last_query = query
        pending = [row for row in self.rows if row.status == "pending"]
        pending.sort(
            key=lambda row: (
                -(int(row.priority or 0)),
                str(row.next_attempt_at or ""),
                str(row.created_at or ""),
            )
        )
        limit_clause = getattr(query, "_limit_clause", None)
        if limit_clause is not None:
            pending = pending[: int(limit_clause.value)]
        return _Result(pending)

    def add(self, row: OutboxModel) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commits += 1


def _row(
    *,
    outbox_id: str = "obx-1",
    task_type: str = "project_case_snapshot",
    attempts: int = 0,
    max_attempts: int = 5,
) -> OutboxModel:
    return OutboxModel(
        outbox_id=outbox_id,
        tenant_id="tenant-1",
        task_type=task_type,
        payload={"ok": True},
        status="pending",
        attempts=attempts,
        max_attempts=max_attempts,
        priority=0,
    )


def test_worker_can_be_instantiated() -> None:
    worker = OutboxWorker(_FakeSession())  # type: ignore[arg-type]

    assert isinstance(worker, OutboxWorker)


def test_register_handler_adds_to_registry() -> None:
    worker = OutboxWorker(_FakeSession())  # type: ignore[arg-type]

    worker.register_handler("project_case_snapshot", lambda _row: None)

    assert "project_case_snapshot" in worker._handlers


def test_register_handler_rejects_blank_task_type() -> None:
    worker = OutboxWorker(_FakeSession())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="task_type is required"):
        worker.register_handler(" ", lambda _row: None)


def test_process_batch_with_no_pending_items_returns_zero() -> None:
    session = _FakeSession()
    worker = OutboxWorker(session)  # type: ignore[arg-type]
    worker.register_handler("project_case_snapshot", lambda _row: None)

    assert worker.process_batch() == 0
    assert session.commits == 0


def test_process_batch_marks_registered_pending_item_completed() -> None:
    row = _row()
    session = _FakeSession(rows=[row])
    seen: list[str] = []
    worker = OutboxWorker(session)  # type: ignore[arg-type]
    worker.register_handler(
        "project_case_snapshot",
        lambda item: seen.append(item.outbox_id),
    )

    processed = worker.process_batch()

    assert processed == 1
    assert seen == ["obx-1"]
    assert row.status == "completed"
    assert row.completed_at is not None
    assert session.commits == 2


def test_process_batch_skips_pending_item_without_registered_handler() -> None:
    row = _row(task_type="unregistered")
    session = _FakeSession(rows=[row])
    worker = OutboxWorker(session)  # type: ignore[arg-type]

    assert worker.process_batch() == 0
    assert row.status == "pending"
    assert session.commits == 0


def test_handler_failure_marks_retryable_before_max_attempts() -> None:
    row = _row(attempts=0, max_attempts=2)
    session = _FakeSession(rows=[row])
    worker = OutboxWorker(session)  # type: ignore[arg-type]

    def fail(_row: OutboxModel) -> None:
        raise RuntimeError("boom")

    worker.register_handler("project_case_snapshot", fail)

    assert worker.process_batch() == 1
    assert row.status == "failed_retryable"
    assert row.attempts == 1
    assert row.last_error == "RuntimeError: boom"


def test_handler_failure_marks_permanent_at_max_attempts() -> None:
    row = _row(attempts=1, max_attempts=2)
    session = _FakeSession(rows=[row])
    worker = OutboxWorker(session)  # type: ignore[arg-type]

    def fail(_row: OutboxModel) -> None:
        raise RuntimeError("boom")

    worker.register_handler("project_case_snapshot", fail)

    assert worker.process_batch() == 1
    assert row.status == "failed_permanent"
    assert row.attempts == 2


def test_pending_query_uses_for_update_skip_locked() -> None:
    session = _FakeSession(rows=[_row()])
    worker = OutboxWorker(session)  # type: ignore[arg-type]
    worker.register_handler("project_case_snapshot", lambda _row: None)

    worker.process_batch()

    assert session.last_query is not None
    assert getattr(session.last_query, "_for_update_arg").skip_locked is True
