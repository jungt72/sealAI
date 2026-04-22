from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.outbox_model import OutboxModel

OutboxHandler = Callable[[OutboxModel], Any]


class OutboxWorker:
    """Minimal Sprint 1 worker scaffold for pending outbox rows."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._handlers: dict[str, OutboxHandler] = {}

    def register_handler(self, task_type: str, handler: OutboxHandler) -> None:
        task_type = str(task_type or "").strip()
        if not task_type:
            raise ValueError("task_type is required")
        self._handlers[task_type] = handler

    def process_batch(self, max_items: int = 10) -> int:
        if max_items <= 0:
            return 0

        rows = list(self._select_pending(max_items))
        processed = 0
        for row in rows:
            handler = self._handlers.get(str(row.task_type))
            if handler is None:
                continue

            row.status = "in_progress"
            self._session.add(row)
            self._session.commit()

            try:
                handler(row)
            except Exception as exc:
                self._mark_failed(row, exc)
            else:
                row.status = "completed"
                row.completed_at = datetime.now(UTC)
                self._session.add(row)
                self._session.commit()
            processed += 1
        return processed

    def _select_pending(self, max_items: int) -> list[OutboxModel]:
        stmt = (
            select(OutboxModel)
            .where(OutboxModel.status == "pending")
            .order_by(
                OutboxModel.priority.desc(),
                OutboxModel.next_attempt_at.asc(),
                OutboxModel.created_at.asc(),
            )
            .limit(max_items)
            .with_for_update(skip_locked=True)
        )
        result = self._session.execute(stmt)
        return list(result.scalars().all())

    def _mark_failed(self, row: OutboxModel, exc: Exception) -> None:
        attempts = int(row.attempts or 0) + 1
        max_attempts = int(row.max_attempts or 1)
        row.attempts = attempts
        row.last_error = f"{type(exc).__name__}: {exc}"
        row.status = (
            "failed_permanent" if attempts >= max_attempts else "failed_retryable"
        )
        self._session.add(row)
        self._session.commit()
