"""Qdrant outbox sync — sealingAI Memory Architecture V1.0, Patch 5.

Drains ``v2_memory_outbox`` (Patch 2 schema, Patch 4 is the only writer so far) and mirrors each
memory item into a DEDICATED Qdrant collection (``sealai_v2_memory``, separate from the Fachkarten
collection — memory is tenant-scoped personal/case content, Fachkarten is manufacturer-neutral
global knowledge; keeping them apart means memory data can never leak into technical-knowledge
retrieval or vice versa by construction, not by a filter someone could get wrong).

Doctrine reminder (this module is NOT the safety boundary): Qdrant is a retrieval index only, never
the source of truth. Whatever this worker mirrors into Qdrant is advisory for RECALL SPEED — a later
patch's retrieval path (Patch 6) MUST re-check the live Postgres status before ever injecting a
result into a prompt. This module's payload mirroring (status/scope/tenant/version) exists so that
check is cheap to reason about, not so it can be skipped.

Retry semantics: an ATTEMPT-COUNT cap (fails permanently after ``max_attempts``), not a time-windowed
exponential backoff — a failed sync retries again on the very next drain pass, up to the cap. This is
a deliberate simplification for this patch (no new column, reuses the existing schema); a real
backoff window (e.g. a ``next_attempt_at`` column) is a reasonable future improvement if the retry
volume ever justifies it, not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2MemoryItem, V2MemoryOutbox
from sealai_v2.knowledge.qdrant_retrieval import (
    _make_client,
    _make_embedder,
    ensure_collection,
)

MEMORY_COLLECTION = "sealai_v2_memory"
_DENSE = "dense"


@dataclass(frozen=True)
class DrainResult:
    claimed: int
    synced: int
    failed_permanently: int
    skipped_missing_item: int


def _make_memory_embedder(settings):
    # Reuses the SAME embedder factory as Fachkarten retrieval (OpenAI text-embedding-3-small by
    # default — RAM-safe, no local model) — deliberately NOT a separate embedding config surface for
    # a second content type; one embedding provider decision for the whole backend.
    return _make_embedder(settings)


def ensure_memory_collection(client, embedder) -> None:
    """Dense-only (no sparse/BM25) — memory items are short personal/case notes, not long technical
    documents where lexical exact-term recall mattered enough to justify hybrid (see
    knowledge/qdrant_retrieval.py's hybrid mode, built for Fachkarten specifically). Revisit if
    memory retrieval quality ever needs it; don't import that complexity speculatively."""
    dim = len(next(iter(embedder.embed(["_warmup_"]))).tolist())
    ensure_collection(client, MEMORY_COLLECTION, dim, sparse=False)


def _claim_pending(s, *, batch_size: int) -> list[V2MemoryOutbox]:
    rows = s.scalars(
        select(V2MemoryOutbox)
        .where(V2MemoryOutbox.status == "pending")
        .order_by(V2MemoryOutbox.id)
        .limit(batch_size)
    ).all()
    for row in rows:
        row.status = "processing"
    s.commit()
    return list(rows)


def _mark_done(s, row: V2MemoryOutbox, *, now: str) -> None:
    row.status = "done"
    row.processed_at = now
    s.commit()


def _mark_retry_or_failed(
    s, row: V2MemoryOutbox, *, now: str, error: str, max_attempts: int
) -> bool:
    """Returns True if this was the FINAL attempt (now permanently failed)."""
    row.attempts += 1
    row.last_error = error[
        :2000
    ]  # bound: last_error is Text but a runaway traceback shouldn't grow unbounded
    row.processed_at = now
    if row.attempts >= max_attempts:
        row.status = "failed"
        s.commit()
        return True
    row.status = "pending"  # retried on the next drain pass (attempt-count cap, not time-windowed)
    s.commit()
    return False


def drain_outbox(
    session_factory: sessionmaker,
    *,
    qdrant_client,
    embedder,
    now: str,
    batch_size: int = 50,
    max_attempts: int = 5,
) -> DrainResult:
    """One drain pass: claim up to ``batch_size`` pending rows, sync each to Qdrant, mark
    done/retry/failed. Safe to call repeatedly (e.g. from a periodic CLI invocation — this codebase
    has no always-on task scheduler; matches the ``ops/`` script convention of periodic invocation
    over inventing new background-process infra)."""
    claimed = synced = failed_permanently = skipped_missing_item = 0
    with session_factory() as s:
        rows = _claim_pending(s, batch_size=batch_size)
        claimed = len(rows)
        for row in rows:
            item_row = s.get(V2MemoryItem, row.memory_item_id)
            if item_row is None:
                # The item was hard-deleted (Patch 14 purge) between enqueue and drain — nothing to
                # sync; the outbox row itself is done (there's nothing left to represent in Qdrant).
                skipped_missing_item += 1
                _mark_done(s, row, now=now)
                continue
            try:
                from qdrant_client.models import (
                    PointStruct,
                )  # lazy, mirrors qdrant_retrieval.py

                vec = next(iter(embedder.embed([item_row.content]))).tolist()
                qdrant_client.upsert(
                    MEMORY_COLLECTION,
                    points=[
                        PointStruct(
                            id=item_row.id,
                            vector={_DENSE: vec},
                            payload={
                                "tenant_id": item_row.tenant_id,
                                "scope": item_row.scope,
                                "scope_id": item_row.scope_id,
                                "status": item_row.status,
                                "version": item_row.version,
                                "type": item_row.type,
                                "semantic_key": item_row.semantic_key,
                            },
                        )
                    ],
                )
                synced += 1
                _mark_done(s, row, now=now)
            except Exception as exc:  # noqa: BLE001 — any Qdrant/network failure is a retry candidate
                if _mark_retry_or_failed(
                    s, row, now=now, error=repr(exc), max_attempts=max_attempts
                ):
                    failed_permanently += 1
    return DrainResult(
        claimed=claimed,
        synced=synced,
        failed_permanently=failed_permanently,
        skipped_missing_item=skipped_missing_item,
    )


def outbox_health(session_factory: sessionmaker) -> dict:
    """Admin/observability summary — counts by outbox status, plus the oldest pending row's age
    proxy (its id, since rows are inserted in order) so a stuck queue is visible at a glance."""
    with session_factory() as s:
        rows = s.execute(select(V2MemoryOutbox.status, V2MemoryOutbox.id)).all()
    by_status: dict[str, int] = {}
    oldest_pending_id: int | None = None
    for status, row_id in rows:
        by_status[status] = by_status.get(status, 0) + 1
        if status == "pending" and (
            oldest_pending_id is None or row_id < oldest_pending_id
        ):
            oldest_pending_id = row_id
    return {
        "total": len(rows),
        "by_status": by_status,
        "oldest_pending_outbox_id": oldest_pending_id,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint (mirrors ``db/migrate.py``'s ``__main__`` shape) — one drain pass, meant for
    periodic invocation (cron/systemd timer), not a long-running process."""
    import argparse
    import sys
    from datetime import datetime, timezone

    from sealai_v2.config.settings import Settings
    from sealai_v2.db.engine import make_engine, make_sessionmaker

    parser = argparse.ArgumentParser(prog="sealai_v2.memory.outbox_worker")
    parser.add_argument("command", choices=["drain", "health"])
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args(argv)

    settings = Settings()
    if not settings.database_url:
        sys.exit(
            "SEALAI_V2_DATABASE_URL not set — the outbox worker needs durable storage"
        )
    sm = make_sessionmaker(make_engine(settings.database_url))

    if args.command == "health":
        print(outbox_health(sm))
        return 0

    if not settings.qdrant_url:
        sys.exit("SEALAI_V2_QDRANT_URL not set — cannot sync to Qdrant")
    client = _make_client(settings)
    embedder = _make_memory_embedder(settings)
    ensure_memory_collection(client, embedder)
    result = drain_outbox(
        sm,
        qdrant_client=client,
        embedder=embedder,
        now=datetime.now(timezone.utc).isoformat(),
        batch_size=args.batch_size,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
