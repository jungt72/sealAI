"""Purge & Compliance — sealingAI Memory Architecture V1.0, Patch 10.

Reaps ``deleted_pending_purge`` items whose grace period (``purge_after``, set by
``db/memory_store.py::transition_status`` at delete time, per ``settings.memory_purge_grace_days``)
has elapsed: hard-deletes the ``V2MemoryItem`` row and its ``V2MemorySource`` rows, writes a
``V2MemoryEvent`` audit row (``to_status="purged"`` — append-only, survives the item row's physical
deletion; matches this schema's no-FK-constraint "referential integrity is an application-layer
concern" convention), and enqueues an ``event_type="delete"`` ``V2MemoryOutbox`` row so the outbox
worker removes the corresponding point from Qdrant.

Doctrine: a purged item must NEVER be usable as context (already covered by
``NEVER_INJECTABLE_STATUSES`` including ``PURGED`` in ``memory/curated.py``) — this module is what
actually makes "purged" true in Postgres, rather than leaving it a terminal status nothing ever
reaches. A ``deleted_pending_purge`` item with no ``purge_after`` set is left alone (never reaped) —
absence of an eligibility timestamp is treated as "not yet eligible", not "eligible immediately";
fail-closed in the direction of NOT deleting data, matching this codebase's general bias.

Not built here (explicitly out of scope, future work): an immediate tenant-wide purge/export admin
API for data-subject-access requests — this module is only the periodic TTL reaper; the final concept
doc's admin export/purge endpoints (§17 No-Go-Liste doesn't block them, but they're a distinct API
surface with their own design questions, e.g. what an "export" payload shape should be) are separate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import (
    V2MemoryEvent,
    V2MemoryItem,
    V2MemoryOutbox,
    V2MemorySource,
)

_PURGE_ACTOR = "system:purge_reaper"


@dataclass(frozen=True)
class PurgeResult:
    reaped: int


def reap_purge_pending(
    session_factory: sessionmaker, *, now: str, batch_size: int = 100
) -> PurgeResult:
    """One reap pass: hard-delete every ``deleted_pending_purge`` item whose ``purge_after`` has
    elapsed. Safe to call repeatedly (periodic CLI invocation — same convention as
    ``outbox_worker.drain_outbox``; this codebase has no always-on task scheduler)."""
    reaped = 0
    with session_factory() as s:
        rows = s.scalars(
            select(V2MemoryItem)
            .where(V2MemoryItem.status == "deleted_pending_purge")
            .where(V2MemoryItem.purge_after.is_not(None))
            .where(V2MemoryItem.purge_after <= now)
            .order_by(V2MemoryItem.id)
            .limit(batch_size)
        ).all()
        for row in rows:
            item_id = row.id
            tenant_id = row.tenant_id
            s.query(V2MemorySource).filter_by(memory_item_id=item_id).delete()
            s.add(
                V2MemoryEvent(
                    memory_item_id=item_id,
                    tenant_id=tenant_id,
                    event_type="purged",
                    from_status="deleted_pending_purge",
                    to_status="purged",
                    actor=_PURGE_ACTOR,
                    note="reaped by the periodic purge job (grace period elapsed)",
                    created_at=now,
                )
            )
            s.add(
                V2MemoryOutbox(
                    memory_item_id=item_id,
                    tenant_id=tenant_id,
                    event_type="delete",
                    payload={"id": item_id, "tenant_id": tenant_id},
                    created_at=now,
                )
            )
            s.delete(row)
            reaped += 1
        s.commit()
    return PurgeResult(reaped=reaped)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint (mirrors ``outbox_worker.main``'s shape) — one reap pass, meant for periodic
    invocation (cron/systemd timer), not a long-running process."""
    import argparse
    import sys
    from datetime import datetime, timezone

    from sealai_v2.config.settings import Settings
    from sealai_v2.db.engine import make_engine, make_sessionmaker

    parser = argparse.ArgumentParser(prog="sealai_v2.memory.purge")
    parser.add_argument("command", choices=["reap"])
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args(argv)

    settings = Settings()
    if not settings.database_url:
        sys.exit(
            "SEALAI_V2_DATABASE_URL not set — the purge reaper needs durable storage"
        )
    sm = make_sessionmaker(make_engine(settings.database_url))

    result = reap_purge_pending(
        sm, now=datetime.now(timezone.utc).isoformat(), batch_size=args.batch_size
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
