"""Qdrant outbox sync worker (Patch 5) — tested against a FAKE Qdrant client (no network), including
a simulated Qdrant outage (the exact scenario the retry/backoff logic exists for).

Patch 9 reconciliation: the outage-retry tests below use hourly-spaced ``now`` timestamps, which
happens to already exceed the real time-windowed backoff (base 30s, doubling, capped at 1h) between
every pair of passes — so their pass-by-pass assertions are unchanged by the backoff upgrade. A new
test below (``test_backoff_window_blocks_an_immediate_retry_pass``) exercises the actual backoff
window directly, since none of the pre-existing tests otherwise would."""

from __future__ import annotations

from sqlalchemy import select

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.memory_store import PostgresMemoryStore
from sealai_v2.db.models import V2MemoryOutbox
from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from sealai_v2.memory.outbox_worker import drain_outbox, outbox_health

import pytest


@pytest.fixture
def db_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'outbox.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


class _ListLike(list):
    def tolist(self):
        return list(self)


class _FakeEmbedder:
    def embed(self, texts):
        return [_ListLike([0.1, 0.2, 0.3]) for _ in texts]


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.upserted: list[tuple[str, list]] = []

    def upsert(self, collection: str, points):
        self.upserted.append((collection, list(points)))


class _AlwaysFailingQdrantClient:
    """Models a Qdrant outage — every upsert raises, the exact scenario the retry/attempt-cap
    logic exists for."""

    def upsert(self, collection: str, points):
        raise ConnectionError("simulated Qdrant outage")


def _item(**overrides) -> MemoryItem:
    defaults = dict(
        id="mem-1",
        tenant_id="tenant-a",
        scope=MemoryScope.SESSION,
        scope_id="session-1",
        type=MemoryType.PREFERENCE,
        status=MemoryStatus.CANDIDATE,
        content="prefers metric units",
        semantic_key="pref:units:metric",
        sources=(MemorySource(kind="user_stated", session_id="session-1"),),
        created_at="2026-07-03T00:00:00Z",
        updated_at="2026-07-03T00:00:00Z",
    )
    defaults.update(overrides)
    return MemoryItem(**defaults)


def _store(url: str) -> PostgresMemoryStore:
    return PostgresMemoryStore(make_sessionmaker(make_engine(url)))


def test_create_candidate_enqueues_and_drain_syncs_it(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    client = _FakeQdrantClient()
    result = drain_outbox(
        sm, qdrant_client=client, embedder=_FakeEmbedder(), now="2026-07-03T01:00:00Z"
    )
    assert result.claimed == 1
    assert result.synced == 1
    assert result.failed_permanently == 0
    assert len(client.upserted) == 1
    collection, points = client.upserted[0]
    assert collection == "sealai_v2_memory"
    assert points[0].id == "mem-1"
    assert points[0].payload["tenant_id"] == "tenant-a"
    assert points[0].payload["status"] == "candidate"


def test_drain_marks_outbox_row_done_after_successful_sync(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=_FakeEmbedder(),
        now="2026-07-03T01:00:00Z",
    )
    with sm() as s:
        row = s.scalars(select(V2MemoryOutbox)).one()
        assert row.status == "done"
        assert row.processed_at == "2026-07-03T01:00:00Z"


def test_drain_is_a_noop_when_nothing_is_pending(db_url):
    sm = make_sessionmaker(make_engine(db_url))
    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=_FakeEmbedder(),
        now="2026-07-03T01:00:00Z",
    )
    assert result == type(result)(claimed=0, synced=0, failed_permanently=0)


def test_simulated_qdrant_outage_retries_then_permanently_fails(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    client = _AlwaysFailingQdrantClient()

    # 4 drain passes with max_attempts=5: attempts 1-4 retry (status back to pending), attempt 5 fails permanently.
    for i in range(4):
        result = drain_outbox(
            sm,
            qdrant_client=client,
            embedder=_FakeEmbedder(),
            now=f"2026-07-03T0{i + 1}:00:00Z",
            max_attempts=5,
        )
        assert result.claimed == 1
        assert result.synced == 0
        assert result.failed_permanently == 0
        with sm() as s:
            row = s.scalars(select(V2MemoryOutbox)).one()
            assert row.status == "pending"  # retried, not yet given up
            assert row.attempts == i + 1

    final = drain_outbox(
        sm,
        qdrant_client=client,
        embedder=_FakeEmbedder(),
        now="2026-07-03T05:00:00Z",
        max_attempts=5,
    )
    assert final.claimed == 1
    assert final.failed_permanently == 1
    with sm() as s:
        row = s.scalars(select(V2MemoryOutbox)).one()
        assert row.status == "failed"
        assert row.attempts == 5
        assert "simulated Qdrant outage" in row.last_error


def test_a_permanently_failed_row_is_never_claimed_again(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    client = _AlwaysFailingQdrantClient()
    for i in range(5):
        drain_outbox(
            sm,
            qdrant_client=client,
            embedder=_FakeEmbedder(),
            now=f"2026-07-03T0{i}:00:00Z",
            max_attempts=5,
        )
    # now try again with a WORKING client — a permanently-failed row must not silently resurrect
    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=_FakeEmbedder(),
        now="2026-07-03T09:00:00Z",
    )
    assert result.claimed == 0


def test_backoff_window_blocks_an_immediate_retry_pass(db_url):
    # Patch 9: real time-windowed backoff (base 30s) replaces the old attempt-count-cap-with-
    # immediate-retry — a drain pass run only 10s after a failure must NOT reclaim the row yet.
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    client = _AlwaysFailingQdrantClient()

    first = drain_outbox(
        sm, qdrant_client=client, embedder=_FakeEmbedder(), now="2026-07-03T01:00:00Z"
    )
    assert first.claimed == 1
    with sm() as s:
        row = s.scalars(select(V2MemoryOutbox)).one()
        assert row.next_attempt_at == "2026-07-03T01:00:30Z"  # base 30s backoff

    too_soon = drain_outbox(
        sm, qdrant_client=client, embedder=_FakeEmbedder(), now="2026-07-03T01:00:10Z"
    )
    assert too_soon.claimed == 0  # backoff window not yet elapsed

    after_window = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=_FakeEmbedder(),
        now="2026-07-03T01:00:31Z",
    )
    assert after_window.claimed == 1
    assert after_window.synced == 1


def test_drain_syncs_from_its_own_snapshot_even_after_the_item_is_hard_deleted(db_url):
    # Patch 9: the outbox row is self-contained (a payload snapshot captured at enqueue time), so a
    # drain no longer needs the source item to still exist in Postgres — it syncs the last known
    # state regardless. Qdrant is advisory-only (doctrine); a purge job enqueueing its own "delete"
    # event is what would actually retract a hard-purged item from Qdrant (Patch 14's own scope).
    store = _store(db_url)
    store.create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        from sealai_v2.db.models import V2MemoryItem

        s.query(V2MemoryItem).filter_by(id="mem-1").delete()
        s.commit()
    client = _FakeQdrantClient()
    result = drain_outbox(
        sm, qdrant_client=client, embedder=_FakeEmbedder(), now="2026-07-03T01:00:00Z"
    )
    assert result.synced == 1
    assert len(client.upserted) == 1
    with sm() as s:
        row = s.scalars(select(V2MemoryOutbox)).one()
        assert row.status == "done"


def test_outbox_health_counts_by_status(db_url):
    _store(db_url).create_candidate(_item())
    _store(db_url).create_candidate(
        _item(id="mem-2", semantic_key="pref:units:imperial")
    )
    sm = make_sessionmaker(make_engine(db_url))
    drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=_FakeEmbedder(),
        now="2026-07-03T01:00:00Z",
    )
    health = outbox_health(sm)
    assert health["total"] == 2
    assert health["by_status"] == {"done": 2}


def test_outbox_health_reports_oldest_pending_id(db_url):
    _store(db_url).create_candidate(_item())
    _store(db_url).create_candidate(
        _item(id="mem-2", semantic_key="pref:units:imperial")
    )
    sm = make_sessionmaker(make_engine(db_url))
    health = outbox_health(sm)
    assert health["by_status"] == {"pending": 2}
    assert health["oldest_pending_outbox_id"] is not None
