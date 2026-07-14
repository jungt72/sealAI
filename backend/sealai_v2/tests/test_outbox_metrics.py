from __future__ import annotations

from datetime import datetime, timezone

import pytest
from prometheus_client import REGISTRY

from sealai_v2.config.settings import Settings
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import V2KnowledgeOutbox, V2MemoryOutbox
from sealai_v2.obs.outbox_metrics import collect_outbox_metrics


@pytest.fixture
def session_factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'metrics.db'}")
    Base.metadata.create_all(engine)
    factory = make_sessionmaker(engine)
    yield factory
    engine.dispose()


def _sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    assert value is not None
    return value


def test_outbox_metrics_are_aggregate_and_fail_closed(session_factory) -> None:
    with session_factory() as session:
        session.add(
            V2MemoryOutbox(
                memory_item_id="mem-opaque",
                tenant_id="tenant-never-a-label",
                event_type="upsert",
                status="pending",
                created_at="2026-07-14T00:00:00Z",
            )
        )
        session.add(
            V2KnowledgeOutbox(
                claim_id="claim-opaque",
                tenant_id="tenant-never-a-label",
                event_type="upsert",
                status="failed",
                created_at="2026-07-14T00:01:00Z",
            )
        )
        session.commit()

    result = collect_outbox_metrics(
        session_factory,
        now=datetime(2026, 7, 14, 0, 10, tzinfo=timezone.utc),
    )

    assert result == {"memory": True, "knowledge": True}
    assert (
        _sample("sealai_v2_outbox_rows", {"queue": "memory", "status": "pending"}) == 1
    )
    assert (
        _sample("sealai_v2_outbox_oldest_pending_seconds", {"queue": "memory"}) == 600
    )
    assert _sample("sealai_v2_projection_backlog_rows", {"queue": "memory"}) == 1
    assert _sample("sealai_v2_projection_backlog_rows", {"queue": "knowledge"}) == 1
    assert (
        _sample("sealai_v2_outbox_metrics_collection_success", {"queue": "knowledge"})
        == 1
    )


def test_collection_failure_is_an_explicit_unhealthy_metric() -> None:
    def unavailable():
        raise RuntimeError("database unavailable")

    result = collect_outbox_metrics(unavailable)  # type: ignore[arg-type]

    assert result == {"memory": False, "knowledge": False}
    assert (
        _sample("sealai_v2_outbox_metrics_collection_success", {"queue": "memory"}) == 0
    )


def test_worker_metrics_port_is_bounded_to_unprivileged_ports() -> None:
    assert Settings(outbox_metrics_port=9101).outbox_metrics_port == 9101
    with pytest.raises(ValueError, match="unprivileged"):
        Settings(outbox_metrics_port=80)
