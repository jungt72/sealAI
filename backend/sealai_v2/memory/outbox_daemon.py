"""Long-running durable outbox worker for the V2 deployment.

The API transaction writes the Postgres outbox row atomically with the memory
change. This process is the only always-on consumer: it retries Qdrant syncs,
backs off during outages, and reclaims stale leases after a worker crash.
"""

from __future__ import annotations

import logging
import signal
from datetime import datetime, timezone
from threading import Event

from sealai_v2.config.settings import Settings
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.knowledge.qdrant_retrieval import _make_client
from sealai_v2.memory.outbox_worker import (
    _make_memory_embedder,
    drain_outbox,
    ensure_memory_collection,
)

_LOG = logging.getLogger("sealai_v2.outbox_daemon")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(settings: Settings, *, stop: Event | None = None) -> None:
    """Run until SIGTERM/SIGINT or ``stop`` is set. Raises configuration errors early."""
    if not settings.database_url:
        raise RuntimeError("SEALAI_V2_DATABASE_URL is required for the outbox worker")
    if not settings.qdrant_url:
        raise RuntimeError("SEALAI_V2_QDRANT_URL is required for the outbox worker")

    stop_event = stop or Event()
    session_factory = make_sessionmaker(make_engine(settings.database_url))
    client = _make_client(settings)
    embedder = _make_memory_embedder(settings)
    ensure_memory_collection(client, embedder)
    _LOG.info(
        "outbox worker started (poll=%ss batch=%s max_attempts=%s claim_timeout=%ss)",
        settings.outbox_poll_interval_s,
        settings.outbox_batch_size,
        settings.outbox_max_attempts,
        settings.outbox_claim_timeout_s,
    )

    while not stop_event.is_set():
        try:
            result = drain_outbox(
                session_factory,
                qdrant_client=client,
                embedder=embedder,
                now=_utc_now(),
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_attempts,
                claim_timeout_seconds=settings.outbox_claim_timeout_s,
            )
            if result.claimed or result.failed_permanently:
                _LOG.info("outbox pass: %s", result)
        except Exception:  # noqa: BLE001 - the loop must survive transient infrastructure faults
            _LOG.exception("outbox pass failed; retrying after poll interval")
        stop_event.wait(settings.outbox_poll_interval_s)

    _LOG.info("outbox worker stopped")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_args: stop.set())
    signal.signal(signal.SIGINT, lambda *_args: stop.set())
    run(Settings(), stop=stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
