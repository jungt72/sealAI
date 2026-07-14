"""Long-running durable outbox worker for the V2 deployment.

The API transaction writes the Postgres outbox row atomically with the memory
change. This process is the only always-on consumer: it retries Qdrant syncs,
backs off during outages, and reclaims stale leases after a worker crash.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from sqlalchemy import text

from sealai_v2.config.settings import Settings
from sealai_v2.obs.log_redaction import configure_safe_logging
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.knowledge.qdrant_retrieval import _make_client, _make_sparse_embedder
from sealai_v2.knowledge.outbox_worker import (
    drain_knowledge_outbox,
    ensure_knowledge_collection,
)
from sealai_v2.memory.outbox_worker import (
    _make_memory_embedder,
    drain_outbox,
    ensure_memory_collection,
)
from sealai_v2.obs.outbox_metrics import collect_outbox_metrics

_LOG = logging.getLogger("sealai_v2.outbox_daemon")
_HEARTBEAT_PATH = Path("/tmp/sealai-v2-outbox-heartbeat")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_heartbeat(path: Path = _HEARTBEAT_PATH) -> None:
    path.write_text(str(time.time()), encoding="ascii")


def healthcheck(
    settings: Settings,
    *,
    heartbeat_path: Path = _HEARTBEAT_PATH,
    now: float | None = None,
) -> dict[str, str]:
    """Prove that the daemon loop is fresh and both durable dependencies answer."""
    if not settings.database_url or not settings.qdrant_url:
        raise RuntimeError("worker database and Qdrant configuration are required")
    heartbeat = float(heartbeat_path.read_text(encoding="ascii"))
    max_age = max(60.0, float(settings.outbox_poll_interval_s) * 3.0)
    age = (time.time() if now is None else now) - heartbeat
    if age < 0 or age > max_age:
        raise RuntimeError(f"worker heartbeat is stale ({age:.1f}s > {max_age:.1f}s)")

    engine = make_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
    client = _make_client(settings)
    client.get_collection(settings.memory_qdrant_collection)
    client.get_collection(settings.qdrant_collection)
    return {"status": "ok", "heartbeat_age_s": f"{age:.1f}"}


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
    sparse_embedder = (
        _make_sparse_embedder(settings) if settings.qdrant_hybrid_enabled else None
    )
    ensure_memory_collection(
        client, embedder, collection=settings.memory_qdrant_collection
    )
    ensure_knowledge_collection(client, settings, embedder)
    _write_heartbeat()
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
                collection=settings.memory_qdrant_collection,
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_attempts,
                claim_timeout_seconds=settings.outbox_claim_timeout_s,
            )
            if result.claimed or result.failed_permanently:
                _LOG.info("memory outbox pass: %s", result)
            knowledge_result = drain_knowledge_outbox(
                session_factory,
                qdrant_client=client,
                embedder=embedder,
                collection=settings.qdrant_collection,
                passage_prefix=settings.embed_passage_prefix,
                sparse_embedder=sparse_embedder,
                now=_utc_now(),
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_attempts,
                claim_timeout_seconds=settings.outbox_claim_timeout_s,
            )
            if knowledge_result.claimed or knowledge_result.failed_permanently:
                _LOG.info("knowledge outbox pass: %s", knowledge_result)
        except Exception:  # noqa: BLE001 - the loop must survive transient infrastructure faults
            _LOG.exception("outbox pass failed; retrying after poll interval")
        metrics_status = collect_outbox_metrics(session_factory)
        if not all(metrics_status.values()):
            _LOG.error("outbox metrics refresh failed")
        _write_heartbeat()
        stop_event.wait(settings.outbox_poll_interval_s)

    _LOG.info("outbox worker stopped")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="sealai_v2.memory.outbox_daemon")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args(argv)
    configure_safe_logging()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings()
    if args.healthcheck:
        healthcheck(settings)
        return 0
    from prometheus_client import start_http_server

    start_http_server(settings.outbox_metrics_port, addr="0.0.0.0")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_args: stop.set())
    signal.signal(signal.SIGINT, lambda *_args: stop.set())
    run(settings, stop=stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
