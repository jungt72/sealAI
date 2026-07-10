"""Drain the technical-knowledge outbox into the derived Qdrant index."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2KnowledgeClaim, V2KnowledgeOutbox
from sealai_v2.knowledge.qdrant_retrieval import _DENSE, ensure_collection

_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 3600


@dataclass(frozen=True)
class KnowledgeDrainResult:
    claimed: int
    synced: int
    failed_permanently: int


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _next_attempt(now: str, attempts: int) -> str:
    delay = min(_BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)), _BACKOFF_MAX_SECONDS)
    return (
        (_parse_iso(now) + timedelta(seconds=delay))
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def ensure_knowledge_collection(client, settings, embedder) -> None:
    dim = len(next(iter(embedder.embed(["_warmup_"]))).tolist())
    ensure_collection(
        client,
        settings.qdrant_collection,
        dim,
        sparse=bool(settings.qdrant_hybrid_enabled),
    )


def _claim_rows(
    session, *, now: str, batch_size: int, claim_timeout_seconds: int
) -> list[V2KnowledgeOutbox]:
    stale_before = (
        (_parse_iso(now) - timedelta(seconds=claim_timeout_seconds))
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    rows = session.scalars(
        select(V2KnowledgeOutbox)
        .where(
            (
                (V2KnowledgeOutbox.status == "pending")
                & (
                    (V2KnowledgeOutbox.next_attempt_at.is_(None))
                    | (V2KnowledgeOutbox.next_attempt_at <= now)
                )
            )
            | (
                (V2KnowledgeOutbox.status == "processing")
                & (
                    V2KnowledgeOutbox.processed_at.is_(None)
                    | (V2KnowledgeOutbox.processed_at <= stale_before)
                )
            )
        )
        .order_by(V2KnowledgeOutbox.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        row.status = "processing"
        row.processed_at = now
    session.commit()
    return list(rows)


def _done(session, row: V2KnowledgeOutbox, *, now: str) -> None:
    row.status = "done"
    row.processed_at = now
    row.next_attempt_at = None
    claim = session.get(V2KnowledgeClaim, row.claim_id)
    payload_version = int((row.payload or {}).get("version") or 0)
    if (
        claim is not None
        and row.event_type == "upsert"
        and claim.version == payload_version
    ):
        claim.qdrant_sync_state = "synced"
        claim.qdrant_synced_version = payload_version
        claim.qdrant_synced_at = now
    session.commit()


def _failed(
    session,
    row: V2KnowledgeOutbox,
    *,
    now: str,
    error: Exception,
    max_attempts: int,
) -> bool:
    row.attempts += 1
    row.last_error = repr(error)[:2000]
    row.processed_at = now
    final = row.attempts >= max_attempts
    row.status = "failed" if final else "pending"
    row.next_attempt_at = None if final else _next_attempt(now, row.attempts)
    claim = session.get(V2KnowledgeClaim, row.claim_id)
    if final and claim is not None:
        claim.qdrant_sync_state = "failed"
    session.commit()
    return final


def drain_knowledge_outbox(
    session_factory: sessionmaker,
    *,
    qdrant_client,
    embedder,
    collection: str,
    passage_prefix: str,
    sparse_embedder=None,
    now: str,
    batch_size: int = 50,
    max_attempts: int = 5,
    claim_timeout_seconds: int = 300,
) -> KnowledgeDrainResult:
    claimed = synced = failed_permanently = 0
    with session_factory() as session:
        rows = _claim_rows(
            session,
            now=now,
            batch_size=batch_size,
            claim_timeout_seconds=claim_timeout_seconds,
        )
        claimed = len(rows)
        # Multiple queued revisions for one claim collapse to the newest event in
        # this claimed window. The older rows are completed together only after
        # the newest projection succeeds, preserving final-state semantics while
        # avoiding redundant embedding and network calls.
        latest_by_claim: dict[str, V2KnowledgeOutbox] = {}
        rows_by_claim: dict[str, list[V2KnowledgeOutbox]] = {}
        for row in rows:
            rows_by_claim.setdefault(row.claim_id, []).append(row)
            latest_by_claim[row.claim_id] = row

        groups = {
            event: [row for row in latest_by_claim.values() if row.event_type == event]
            for event in ("delete", "upsert")
        }
        unknown = [
            row for row in latest_by_claim.values() if row.event_type not in groups
        ]
        for row in unknown:
            error = ValueError(f"unknown knowledge outbox event {row.event_type!r}")
            for queued in rows_by_claim[row.claim_id]:
                if _failed(
                    session,
                    queued,
                    now=now,
                    error=error,
                    max_attempts=max_attempts,
                ):
                    failed_permanently += 1

        for event_type, effective_rows in groups.items():
            if not effective_rows:
                continue
            try:
                if event_type == "delete":
                    qdrant_client.delete(
                        collection,
                        points_selector=[row.claim_id for row in effective_rows],
                        wait=True,
                    )
                else:
                    from qdrant_client.models import PointStruct, SparseVector

                    payloads = [dict(row.payload or {}) for row in effective_rows]
                    if any(not payload.get("claim_text") for payload in payloads):
                        raise ValueError("knowledge outbox upsert has no claim_text")
                    dense = list(
                        embedder.embed(
                            [
                                f"{passage_prefix}{payload['claim_text']}"
                                for payload in payloads
                            ]
                        )
                    )
                    sparse = (
                        list(
                            sparse_embedder.embed(
                                [payload["claim_text"] for payload in payloads]
                            )
                        )
                        if sparse_embedder is not None
                        else None
                    )
                    if len(dense) != len(payloads):
                        raise RuntimeError(
                            "embedding provider returned an incomplete dense batch: "
                            f"{len(dense)}/{len(payloads)}"
                        )
                    if sparse is not None and len(sparse) != len(payloads):
                        raise RuntimeError(
                            "embedding provider returned an incomplete sparse batch: "
                            f"{len(sparse)}/{len(payloads)}"
                        )
                    points = []
                    for index, (row, payload, dense_vector) in enumerate(
                        zip(effective_rows, payloads, dense)
                    ):
                        vectors: dict = {_DENSE: dense_vector.tolist()}
                        if sparse is not None:
                            vectors["sparse"] = SparseVector(
                                indices=sparse[index].indices.tolist(),
                                values=sparse[index].values.tolist(),
                            )
                        points.append(
                            PointStruct(
                                id=row.claim_id,
                                vector=vectors,
                                payload=payload,
                            )
                        )
                    qdrant_client.upsert(collection, points=points, wait=True)

                for row in effective_rows:
                    for queued in rows_by_claim[row.claim_id]:
                        synced += 1
                        _done(session, queued, now=now)
            except Exception as exc:  # noqa: BLE001 - infrastructure failures are retried
                for row in effective_rows:
                    for queued in rows_by_claim[row.claim_id]:
                        if _failed(
                            session,
                            queued,
                            now=now,
                            error=exc,
                            max_attempts=max_attempts,
                        ):
                            failed_permanently += 1
    return KnowledgeDrainResult(claimed, synced, failed_permanently)


def pending_count(session_factory: sessionmaker) -> int:
    with session_factory() as session:
        return len(
            session.scalars(
                select(V2KnowledgeOutbox.id).where(
                    V2KnowledgeOutbox.status.in_(("pending", "processing"))
                )
            ).all()
        )


def unresolved_count(session_factory: sessionmaker) -> int:
    with session_factory() as session:
        return len(
            session.scalars(
                select(V2KnowledgeOutbox.id).where(V2KnowledgeOutbox.status != "done")
            ).all()
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    from sealai_v2.config.settings import Settings
    from sealai_v2.db.engine import make_engine, make_sessionmaker
    from sealai_v2.knowledge.qdrant_retrieval import (
        _make_client,
        _make_embedder,
        _make_sparse_embedder,
    )

    parser = argparse.ArgumentParser(prog="sealai_v2.knowledge.outbox_worker")
    parser.add_argument("command", choices=("drain", "drain-all"))
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args(argv)
    settings = Settings()
    if not settings.database_url or not settings.qdrant_url:
        raise SystemExit("knowledge outbox requires Postgres and Qdrant")
    session_factory = make_sessionmaker(make_engine(settings.database_url))
    client = _make_client(settings)
    embedder = _make_embedder(settings)
    sparse_embedder = (
        _make_sparse_embedder(settings) if settings.qdrant_hybrid_enabled else None
    )
    ensure_knowledge_collection(client, settings, embedder)
    total_claimed = total_synced = total_failed = 0
    while True:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = drain_knowledge_outbox(
            session_factory,
            qdrant_client=client,
            embedder=embedder,
            sparse_embedder=sparse_embedder,
            collection=settings.qdrant_collection,
            passage_prefix=settings.embed_passage_prefix,
            now=now,
            batch_size=args.batch_size,
            max_attempts=settings.outbox_max_attempts,
            claim_timeout_seconds=settings.outbox_claim_timeout_s,
        )
        total_claimed += result.claimed
        total_synced += result.synced
        total_failed += result.failed_permanently
        if args.command != "drain-all" or result.claimed == 0:
            break
    print(
        KnowledgeDrainResult(
            claimed=total_claimed,
            synced=total_synced,
            failed_permanently=total_failed,
        )
    )
    unresolved = unresolved_count(session_factory)
    if unresolved:
        print(f"knowledge outbox unresolved rows: {unresolved}")
    return 1 if total_failed or unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
