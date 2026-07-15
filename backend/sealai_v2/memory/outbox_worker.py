"""Qdrant outbox sync — sealingAI Memory Architecture V1.0, Patch 5.

Drains ``v2_memory_outbox`` (Patch 2 schema, Patch 4 is the only writer so far) and mirrors each
memory item into a DEDICATED Qdrant collection (separate from the Fachkarten
collection — memory is tenant-scoped personal/case content, Fachkarten is manufacturer-neutral
global knowledge; keeping them apart means memory data can never leak into technical-knowledge
retrieval or vice versa by construction, not by a filter someone could get wrong).

Doctrine reminder (this module is NOT the safety boundary): Qdrant is a retrieval index only, never
the source of truth. Whatever this worker mirrors into Qdrant is advisory for RECALL SPEED — a later
patch's retrieval path (Patch 6) MUST re-check the live Postgres status before ever injecting a
result into a prompt. This module's payload mirroring (status/scope/tenant/version) exists so that
check is cheap to reason about, not so it can be skipped.

Patch 9 reconciliation (final concept doc §6/§7), two changes:

- The drain reads each row's own snapshotted ``payload`` (captured by the writer at enqueue time,
  ``db/memory_store.py::_outbox_payload``) instead of re-reading ``V2MemoryItem`` live. This is the
  real outbox-pattern shape: the row is self-contained, so a drain syncs exactly the state that was
  committed at enqueue time, not whatever the item happens to look like by the time the worker gets
  to it. A consequence: this worker no longer checks whether the source item still exists in
  Postgres — a hard-purged item's already-enqueued rows still sync their last known state.
- Retry semantics upgraded from an ATTEMPT-COUNT cap with immediate next-pass retry to a real
  time-windowed exponential backoff via ``next_attempt_at`` (base 30s, doubling per attempt, capped
  at 1h) — a failed sync no longer hammers Qdrant on every single drain pass while it's down.

Patch 10 (Purge & Compliance): ``memory/purge.py``'s reap job now enqueues ``event_type="delete"``
rows here for hard-purged items. This drain FIXES a latent gap from the Patch 9 reconciliation above:
every row was previously synced via ``qdrant_client.upsert`` regardless of ``event_type`` — a "delete"
row would have silently RE-UPSERTED the item's last known state into Qdrant instead of removing it
(harmless before Patch 10, since nothing ever enqueued a "delete" row until now, but a real bug had
this drain ever been exercised with one). Now branches on ``row.event_type``: "delete" calls
``qdrant_client.delete``, "upsert" is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2MemoryOutbox
from sealai_v2.knowledge.qdrant_retrieval import (
    _make_client,
    _make_embedder,
    ensure_collection,
)
from sealai_v2.security.cost_control import (
    EmbeddingServiceAdmission,
    ProviderServiceUnavailable,
    build_embedding_service_admission,
    classify_outbox_failure,
    embed_with_service_admission,
    remote_embedding_enabled,
    validate_remote_embedding_inputs,
    validate_embedding_worker_limits,
)

MEMORY_COLLECTION = "sealai_v2_memory"
_DENSE = "dense"
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 3600


@dataclass(frozen=True)
class DrainResult:
    claimed: int
    synced: int
    failed_permanently: int


def _make_memory_embedder(settings):
    # Reuses the SAME embedder factory as Fachkarten retrieval (OpenAI text-embedding-3-small by
    # default — RAM-safe, no local model) — deliberately NOT a separate embedding config surface for
    # a second content type; one embedding provider decision for the whole backend.
    # The worker owns retries explicitly: every later attempt receives a fresh durable admission.
    # Disable SDK-internal retries so one admission can never hide multiple paid HTTP attempts.
    return _make_embedder(settings, max_retries=0)


def ensure_memory_collection(
    client,
    embedder,
    *,
    collection: str = MEMORY_COLLECTION,
    remote_embeddings: bool = False,
    service_admission: EmbeddingServiceAdmission | None = None,
) -> None:
    """Dense-only (no sparse/BM25) — memory items are short personal/case notes, not long technical
    documents where lexical exact-term recall mattered enough to justify hybrid (see
    knowledge/qdrant_retrieval.py's hybrid mode, built for Fachkarten specifically). Revisit if
    memory retrieval quality ever needs it; don't import that complexity speculatively."""
    vectors = embed_with_service_admission(
        embedder,
        ("_warmup_",),
        remote=remote_embeddings,
        admission=service_admission,
    )
    if len(vectors) != 1:
        raise RuntimeError("embedding provider returned an incomplete warmup batch")
    dim = len(vectors[0].tolist())
    ensure_collection(client, collection, dim, sparse=False)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _compute_next_attempt_at(now: str, attempts: int) -> str:
    """Exponential backoff, deterministic given ``now``/``attempts`` — no live clock read here,
    matches this codebase's "``now`` is always a caller-supplied parameter" discipline."""
    delay_seconds = min(
        _BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)), _BACKOFF_MAX_SECONDS
    )
    when = _parse_iso(now) + timedelta(seconds=delay_seconds)
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _claim_pending(s, *, batch_size: int, now: str) -> list[V2MemoryOutbox]:
    return _claim_pending_with_timeout(
        s, batch_size=batch_size, now=now, claim_timeout_seconds=300
    )


def _claim_pending_with_timeout(
    s, *, batch_size: int, now: str, claim_timeout_seconds: int
) -> list[V2MemoryOutbox]:
    stale_before = (
        (_parse_iso(now) - timedelta(seconds=claim_timeout_seconds))
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    rows = s.scalars(
        select(V2MemoryOutbox)
        .where(
            (
                (V2MemoryOutbox.status == "pending")
                & (
                    (V2MemoryOutbox.next_attempt_at.is_(None))
                    | (V2MemoryOutbox.next_attempt_at <= now)
                )
            )
            | (
                (V2MemoryOutbox.status == "processing")
                & (
                    V2MemoryOutbox.processed_at.is_(None)
                    | (V2MemoryOutbox.processed_at <= stale_before)
                )
            )
        )
        .order_by(V2MemoryOutbox.id)
        .limit(batch_size)
    ).all()
    for row in rows:
        row.status = "processing"
        # ``processed_at`` is also the lease heartbeat. It is updated again when
        # the attempt is finalized, so a crashed worker can be reclaimed safely.
        row.processed_at = now
    s.commit()
    return list(rows)


def _mark_done(s, row: V2MemoryOutbox, *, now: str) -> None:
    row.status = "done"
    row.processed_at = now
    row.next_attempt_at = None
    s.commit()


def _mark_retry_or_failed(
    s, row: V2MemoryOutbox, *, now: str, error: BaseException, max_attempts: int
) -> bool:
    """Returns True if this was the FINAL attempt (now permanently failed)."""
    row.attempts += 1
    row.last_error = classify_outbox_failure(error)
    row.processed_at = now
    if row.attempts >= max_attempts:
        row.status = "failed"
        row.next_attempt_at = None
        s.commit()
        return True
    row.status = (
        "pending"  # retried once the backoff window elapses (see _claim_pending)
    )
    row.next_attempt_at = _compute_next_attempt_at(now, row.attempts)
    s.commit()
    return False


def drain_outbox(
    session_factory: sessionmaker,
    *,
    qdrant_client,
    embedder,
    now: str,
    collection: str = MEMORY_COLLECTION,
    batch_size: int = 50,
    max_attempts: int = 5,
    claim_timeout_seconds: int = 300,
    remote_embeddings: bool = False,
    service_admission: EmbeddingServiceAdmission | None = None,
    prepare_embeddings: Callable[
        [], tuple[object, EmbeddingServiceAdmission | None] | None
    ]
    | None = None,
) -> DrainResult:
    """One drain pass: claim up to ``batch_size`` pending rows whose backoff window (if any) has
    elapsed, sync each to Qdrant from its own snapshotted ``payload``, mark done/retry/failed. Safe
    to call repeatedly (e.g. from a periodic CLI invocation — this codebase has no always-on task
    scheduler; matches the ``ops/`` script convention of periodic invocation over inventing new
    background-process infra)."""
    # Positivity is always invalid. Remote-only cost bounds are checked after claim so a daemon can
    # still service an empty or delete-only queue without opening the paid-provider control path.
    validate_embedding_worker_limits(batch_size, max_attempts, remote=False)
    claimed = synced = failed_permanently = 0
    with session_factory() as s:
        rows = _claim_pending_with_timeout(
            s,
            batch_size=batch_size,
            now=now,
            claim_timeout_seconds=claim_timeout_seconds,
        )
        claimed = len(rows)
        upsert_rows: list[V2MemoryOutbox] = []
        for row in rows:
            payload = row.payload or {}
            point_id = payload.get("id", row.memory_item_id)
            if row.event_type != "delete":
                upsert_rows.append(row)
                continue
            try:
                qdrant_client.delete(collection, points_selector=[point_id])
                synced += 1
                _mark_done(s, row, now=now)
            except Exception as exc:  # noqa: BLE001 - infrastructure failures are retried
                if _mark_retry_or_failed(
                    s, row, now=now, error=exc, max_attempts=max_attempts
                ):
                    failed_permanently += 1

        if upsert_rows:
            payloads = [dict(row.payload or {}) for row in upsert_rows]
            texts = tuple(payload.get("content", "") for payload in payloads)
            try:
                validate_embedding_worker_limits(
                    batch_size, max_attempts, remote=remote_embeddings
                )
                if remote_embeddings:
                    # Reject corrupt/oversize payloads before a lazy collection warmup can consume
                    # an admission or construct the paid adapter.
                    validate_remote_embedding_inputs(texts)
                # Collection discovery itself embeds a warmup input.  Keep it lazy so an empty or
                # delete-only queue performs neither provider admission nor provider I/O.
                batch_embedder = embedder
                batch_admission = service_admission
                if prepare_embeddings is not None:
                    prepared = prepare_embeddings()
                    if prepared is not None:
                        batch_embedder, batch_admission = prepared
                if batch_embedder is None:
                    raise ProviderServiceUnavailable(
                        "outbox embedding adapter is unavailable"
                    )
                vectors = embed_with_service_admission(
                    batch_embedder,
                    texts,
                    remote=remote_embeddings,
                    admission=batch_admission,
                )
                if len(vectors) != len(upsert_rows):
                    raise RuntimeError(
                        "embedding provider returned an incomplete memory batch: "
                        f"{len(vectors)}/{len(upsert_rows)}"
                    )
            except Exception as exc:  # noqa: BLE001 - provider/control failures are retried
                for row in upsert_rows:
                    if _mark_retry_or_failed(
                        s, row, now=now, error=exc, max_attempts=max_attempts
                    ):
                        failed_permanently += 1
            else:
                from qdrant_client.models import PointStruct

                for row, payload, vector in zip(upsert_rows, payloads, vectors):
                    point_id = payload.get("id", row.memory_item_id)
                    try:
                        qdrant_client.upsert(
                            collection,
                            points=[
                                PointStruct(
                                    id=point_id,
                                    vector={_DENSE: vector.tolist()},
                                    payload={
                                        "tenant_id": payload.get("tenant_id"),
                                        "owner_subject": payload.get("owner_subject"),
                                        "scope": payload.get("scope"),
                                        "scope_id": payload.get("scope_id"),
                                        "status": payload.get("status"),
                                        "version": payload.get("version"),
                                        "type": payload.get("type"),
                                        "semantic_key": payload.get("semantic_key"),
                                    },
                                )
                            ],
                        )
                        synced += 1
                        _mark_done(s, row, now=now)
                    except Exception as exc:  # noqa: BLE001 - infrastructure failures are retried
                        if _mark_retry_or_failed(
                            s,
                            row,
                            now=now,
                            error=exc,
                            max_attempts=max_attempts,
                        ):
                            failed_permanently += 1
    return DrainResult(
        claimed=claimed,
        synced=synced,
        failed_permanently=failed_permanently,
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
    remote = remote_embedding_enabled(settings)
    validate_embedding_worker_limits(
        args.batch_size, settings.outbox_max_attempts, remote=False
    )
    client = _make_client(settings)
    embedder = None
    service_admission = None
    admission_ready = False
    collection_ready = False

    def prepare_embeddings() -> tuple[object, EmbeddingServiceAdmission | None]:
        nonlocal admission_ready, collection_ready, embedder, service_admission
        validate_embedding_worker_limits(
            args.batch_size, settings.outbox_max_attempts, remote=remote
        )
        if not admission_ready:
            service_admission = build_embedding_service_admission(
                settings, sm, service="memory_outbox"
            )
            admission_ready = True
        if embedder is None:
            # Paid adapter/key construction stays behind the kill switch and durable authority.
            embedder = _make_memory_embedder(settings)
        if collection_ready:
            return embedder, service_admission
        ensure_memory_collection(
            client,
            embedder,
            collection=settings.memory_qdrant_collection,
            remote_embeddings=remote,
            service_admission=service_admission,
        )
        collection_ready = True
        return embedder, service_admission

    result = drain_outbox(
        sm,
        qdrant_client=client,
        embedder=embedder,
        now=datetime.now(timezone.utc).isoformat(),
        collection=settings.memory_qdrant_collection,
        batch_size=args.batch_size,
        max_attempts=settings.outbox_max_attempts,
        claim_timeout_seconds=settings.outbox_claim_timeout_s,
        remote_embeddings=remote,
        service_admission=service_admission,
        prepare_embeddings=prepare_embeddings,
    )
    print(result)
    return 1 if result.synced != result.claimed or result.failed_permanently else 0


if __name__ == "__main__":
    raise SystemExit(main())
