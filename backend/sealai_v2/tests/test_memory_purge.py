"""Purge & Compliance reaper (Patch 10) — proves: only deleted_pending_purge items with an ELAPSED
purge_after get hard-deleted; a purged item leaves a durable audit trail (V2MemoryEvent) even though
its own row is gone; a purge enqueues a Qdrant "delete" outbox event; items missing purge_after or not
yet eligible or in any other status are left completely untouched."""

from __future__ import annotations

from sqlalchemy import select

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.memory_store import PostgresMemoryStore
from sealai_v2.db.models import (
    V2MemoryEvent,
    V2MemoryItem,
    V2MemoryOutbox,
    V2MemorySource,
)
from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from sealai_v2.memory.purge import PurgeResult, reap_purge_pending

import pytest


@pytest.fixture
def db_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'purge.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def _store(url: str) -> PostgresMemoryStore:
    return PostgresMemoryStore(make_sessionmaker(make_engine(url)))


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


def _soft_delete(store, item_id="mem-1", *, purge_after="2026-08-01T00:00:00Z"):
    store.transition_status(
        tenant_id="tenant-a",
        item_id=item_id,
        to_status=MemoryStatus.DELETED_PENDING_PURGE,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
        purge_after=purge_after,
    )


def test_reap_is_a_noop_when_nothing_is_deleted_pending_purge(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    result = reap_purge_pending(sm, now="2026-09-01T00:00:00Z")
    assert result == PurgeResult(reaped=0)


def test_reap_ignores_items_whose_grace_period_has_not_yet_elapsed(db_url):
    store = _store(db_url)
    store.create_candidate(_item())
    _soft_delete(store, purge_after="2026-08-01T00:00:00Z")
    sm = make_sessionmaker(make_engine(db_url))
    result = reap_purge_pending(sm, now="2026-07-15T00:00:00Z")  # before purge_after
    assert result.reaped == 0
    with sm() as s:
        assert s.get(V2MemoryItem, "mem-1") is not None


def test_reap_ignores_items_with_no_purge_after_set(db_url):
    # A deleted_pending_purge item with no purge_after is "not yet eligible", not "eligible
    # immediately" — fail-closed in the direction of not deleting data.
    store = _store(db_url)
    store.create_candidate(_item())
    _soft_delete(store, purge_after=None)
    sm = make_sessionmaker(make_engine(db_url))
    result = reap_purge_pending(sm, now="2026-12-01T00:00:00Z")
    assert result.reaped == 0
    with sm() as s:
        assert s.get(V2MemoryItem, "mem-1") is not None


def test_reap_hard_deletes_an_eligible_item_and_its_sources(db_url):
    store = _store(db_url)
    store.create_candidate(_item())
    _soft_delete(store, purge_after="2026-08-01T00:00:00Z")
    sm = make_sessionmaker(make_engine(db_url))
    result = reap_purge_pending(sm, now="2026-09-01T00:00:00Z")
    assert result.reaped == 1
    with sm() as s:
        assert s.get(V2MemoryItem, "mem-1") is None
        sources = s.scalars(
            select(V2MemorySource).where(V2MemorySource.memory_item_id == "mem-1")
        ).all()
        assert sources == []


def test_reap_writes_a_purged_audit_event_that_survives_the_item_deletion(db_url):
    store = _store(db_url)
    store.create_candidate(_item())
    _soft_delete(store, purge_after="2026-08-01T00:00:00Z")
    sm = make_sessionmaker(make_engine(db_url))
    reap_purge_pending(sm, now="2026-09-01T00:00:00Z")
    with sm() as s:
        events = s.scalars(
            select(V2MemoryEvent)
            .where(V2MemoryEvent.memory_item_id == "mem-1")
            .order_by(V2MemoryEvent.id)
        ).all()
        assert [e.to_status for e in events] == ["deleted_pending_purge", "purged"]
        assert events[-1].actor == "system:purge_reaper"
        assert s.get(V2MemoryItem, "mem-1") is None  # item row gone, event row is not


def test_reap_enqueues_a_qdrant_delete_outbox_event(db_url):
    store = _store(db_url)
    store.create_candidate(_item())
    _soft_delete(store, purge_after="2026-08-01T00:00:00Z")
    sm = make_sessionmaker(make_engine(db_url))
    reap_purge_pending(sm, now="2026-09-01T00:00:00Z")
    with sm() as s:
        outbox = s.scalars(
            select(V2MemoryOutbox)
            .where(V2MemoryOutbox.memory_item_id == "mem-1")
            .order_by(V2MemoryOutbox.id)
        ).all()
        assert [o.event_type for o in outbox] == ["upsert", "upsert", "delete"]
        delete_row = outbox[-1]
        assert delete_row.payload == {"id": "mem-1", "tenant_id": "tenant-a"}


def test_reap_never_touches_items_in_other_statuses(db_url):
    store = _store(db_url)
    store.create_candidate(_item())  # still a candidate — never soft-deleted
    sm = make_sessionmaker(make_engine(db_url))
    result = reap_purge_pending(sm, now="2026-09-01T00:00:00Z")
    assert result.reaped == 0
    with sm() as s:
        assert s.get(V2MemoryItem, "mem-1") is not None


def test_reap_only_touches_eligible_rows_leaves_others_across_a_mixed_batch(db_url):
    store = _store(db_url)
    store.create_candidate(_item(id="mem-eligible", semantic_key="k1"))
    store.create_candidate(_item(id="mem-not-yet", semantic_key="k2"))
    store.create_candidate(_item(id="mem-untouched", semantic_key="k3"))
    _soft_delete(store, "mem-eligible", purge_after="2026-08-01T00:00:00Z")
    _soft_delete(store, "mem-not-yet", purge_after="2026-12-01T00:00:00Z")
    sm = make_sessionmaker(make_engine(db_url))
    result = reap_purge_pending(sm, now="2026-09-01T00:00:00Z")
    assert result.reaped == 1
    with sm() as s:
        assert s.get(V2MemoryItem, "mem-eligible") is None
        assert s.get(V2MemoryItem, "mem-not-yet") is not None
        assert s.get(V2MemoryItem, "mem-untouched") is not None
