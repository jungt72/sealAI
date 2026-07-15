"""Low-cardinality metrics for the Postgres-authoritative Qdrant outboxes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from prometheus_client import Gauge
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2KnowledgeOutbox, V2MemoryOutbox

_STATUSES = ("pending", "processing", "done", "failed", "unknown")
_QUEUES: tuple[tuple[str, Any], ...] = (
    ("memory", V2MemoryOutbox),
    ("knowledge", V2KnowledgeOutbox),
)

_OUTBOX_ROWS = Gauge(
    "sealai_v2_outbox_rows",
    "Rows in a durable V2 Postgres outbox.",
    ("queue", "status"),
)
_OUTBOX_OLDEST_PENDING_SECONDS = Gauge(
    "sealai_v2_outbox_oldest_pending_seconds",
    "Age of the oldest unresolved V2 outbox row.",
    ("queue",),
)
_PROJECTION_BACKLOG_ROWS = Gauge(
    "sealai_v2_projection_backlog_rows",
    "Unresolved Postgres-authoritative outbox rows awaiting projection handling.",
    ("queue",),
)
_COLLECTION_SUCCESS = Gauge(
    "sealai_v2_outbox_metrics_collection_success",
    "Whether the latest Postgres outbox metrics collection succeeded.",
    ("queue",),
)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _snapshot(
    session_factory: sessionmaker,
    model: Any,
    *,
    now: datetime,
) -> tuple[dict[str, int], float]:
    with session_factory() as session:
        rows = session.execute(
            select(model.status, func.count(model.id)).group_by(model.status)
        ).all()
        oldest = session.scalar(
            select(func.min(model.created_at)).where(
                model.status.in_(("pending", "processing"))
            )
        )

    counts = {status: 0 for status in _STATUSES}
    for raw_status, raw_count in rows:
        status = raw_status if raw_status in _STATUSES[:-1] else "unknown"
        counts[status] += int(raw_count)
    age_seconds = (
        max(0.0, (now - _parse_timestamp(oldest)).total_seconds()) if oldest else 0.0
    )
    return counts, age_seconds


def collect_outbox_metrics(
    session_factory: sessionmaker,
    *,
    now: datetime | None = None,
) -> dict[str, bool]:
    """Refresh aggregate outbox state without leaking row or tenant identifiers.

    A failed query leaves the last state samples intact and flips the dedicated
    collection-success gauge to zero, so a database outage cannot look healthy.
    """
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result: dict[str, bool] = {}
    for queue, model in _QUEUES:
        try:
            counts, oldest_age = _snapshot(
                session_factory,
                model,
                now=observed_at,
            )
        except Exception:  # noqa: BLE001 - failure is represented by a fail-closed metric
            _COLLECTION_SUCCESS.labels(queue).set(0)
            result[queue] = False
            continue

        for status in _STATUSES:
            _OUTBOX_ROWS.labels(queue, status).set(counts[status])
        _OUTBOX_OLDEST_PENDING_SECONDS.labels(queue).set(oldest_age)
        _PROJECTION_BACKLOG_ROWS.labels(queue).set(
            counts["pending"]
            + counts["processing"]
            + counts["failed"]
            + counts["unknown"]
        )
        _COLLECTION_SUCCESS.labels(queue).set(1)
        result[queue] = True
    return result
