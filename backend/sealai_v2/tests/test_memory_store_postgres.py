"""PostgresMemoryStore — restart-survival + tenant isolation (mirrors test_persistence_store.py's
pattern against the sqlite-backed adapter; same dialect-agnostic SQL runs against Postgres in prod)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.memory_store import (
    InvalidMemoryTransition,
    MemoryItemNotFound,
    PostgresMemoryStore,
)
from sealai_v2.db.models import V2MemoryEvent, V2MemoryOutbox
from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from sealai_v2.security.tenant import TenantScopeError


@pytest.fixture
def db_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'memory_store.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def _store(url: str) -> PostgresMemoryStore:
    # a NEW engine/sessionmaker each call → re-instantiating against the same file models a fresh
    # process (the restart-survival proof), same as test_persistence_store.py's _mem() helper.
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


def test_create_candidate_survives_a_fresh_store_instance(db_url):
    _store(db_url).create_candidate(_item())
    fresh = _store(db_url)  # models a process restart against the same DB
    items = fresh.list_items(tenant_id="tenant-a")
    assert len(items) == 1
    assert items[0].content == "prefers metric units"
    assert items[0].sources == (
        MemorySource(kind="user_stated", session_id="session-1"),
    )


def test_tenant_isolation_no_cross_tenant_read(db_url):
    _store(db_url).create_candidate(_item(tenant_id="tenant-a"))
    other = _store(db_url).list_items(tenant_id="tenant-b")
    assert other == ()
    summary = _store(db_url).summary(tenant_id="tenant-b")
    assert summary == {"total": 0, "by_status": {}, "by_scope": {}}


def test_list_items_rejects_blank_tenant(db_url):
    store = _store(db_url)
    with pytest.raises(TenantScopeError):
        store.list_items(tenant_id="")


def test_case_id_is_denormalized_from_scope_at_write_time(db_url):
    store = _store(db_url)
    store.create_candidate(
        _item(
            id="mem-case",
            scope=MemoryScope.CASE,
            scope_id="case-42",
            type=MemoryType.CASE_PARAMETER,
            semantic_key="case:case-42:medium",
        )
    )
    filtered = store.list_items(tenant_id="tenant-a", case_id="case-42")
    assert len(filtered) == 1 and filtered[0].id == "mem-case"
    not_a_project = store.list_items(tenant_id="tenant-a", project_id="case-42")
    assert (
        not_a_project == ()
    )  # case-scoped item must not leak into a project_id filter


# --- Patch 4: status transitions (confirm/reject/deprecate/delete) ---


def test_get_item_returns_none_for_unknown_id(db_url):
    assert _store(db_url).get_item(tenant_id="tenant-a", item_id="nope") is None


def test_get_item_returns_none_across_tenants(db_url):
    _store(db_url).create_candidate(_item(tenant_id="tenant-a"))
    assert _store(db_url).get_item(tenant_id="tenant-b", item_id="mem-1") is None


def test_transition_status_updates_status_bumps_version_stamps_updated_at(db_url):
    _store(db_url).create_candidate(_item())
    updated = _store(db_url).transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.CONFIRMED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    assert updated.status == MemoryStatus.CONFIRMED
    assert updated.version == 2
    assert updated.updated_at == "2026-07-03T01:00:00Z"


def test_transition_status_survives_a_fresh_store_instance(db_url):
    _store(db_url).create_candidate(_item())
    _store(db_url).transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.CONFIRMED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    fresh = _store(db_url).get_item(tenant_id="tenant-a", item_id="mem-1")
    assert fresh.status == MemoryStatus.CONFIRMED


def test_transition_status_raises_not_found_for_unknown_id(db_url):
    store = _store(db_url)
    with pytest.raises(MemoryItemNotFound):
        store.transition_status(
            tenant_id="tenant-a",
            item_id="nope",
            to_status=MemoryStatus.CONFIRMED,
            actor="user-1",
            now="2026-07-03T01:00:00Z",
        )


def test_transition_status_raises_not_found_across_tenants(db_url):
    _store(db_url).create_candidate(_item(tenant_id="tenant-a"))
    with pytest.raises(MemoryItemNotFound):
        _store(db_url).transition_status(
            tenant_id="tenant-b",
            item_id="mem-1",
            to_status=MemoryStatus.CONFIRMED,
            actor="user-1",
            now="2026-07-03T01:00:00Z",
        )


def test_transition_status_rejects_illegal_transition(db_url):
    _store(db_url).create_candidate(_item())
    store = _store(db_url)
    store.transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.REJECTED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    with pytest.raises(InvalidMemoryTransition):
        store.transition_status(
            tenant_id="tenant-a",
            item_id="mem-1",
            to_status=MemoryStatus.CONFIRMED,
            actor="user-1",
            now="2026-07-03T02:00:00Z",
        )


def test_transition_status_writes_a_memory_event(db_url):
    _store(db_url).create_candidate(_item())
    _store(db_url).transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.CONFIRMED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
        note="confirmed via Right Rail",
    )
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        events = s.scalars(
            select(V2MemoryEvent).where(V2MemoryEvent.memory_item_id == "mem-1")
        ).all()
        assert len(events) == 1
        ev = events[0]
        assert ev.from_status == "candidate" and ev.to_status == "confirmed"
        assert ev.actor == "user-1"
        assert ev.note == "confirmed via Right Rail"


def test_transition_status_enqueues_an_outbox_upsert(db_url):
    _store(db_url).create_candidate(_item())
    _store(db_url).transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.CONFIRMED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        rows = s.scalars(
            select(V2MemoryOutbox).where(V2MemoryOutbox.memory_item_id == "mem-1")
        ).all()
        assert len(rows) == 1
        assert rows[0].operation == "upsert"
        assert rows[0].status == "pending"


def test_two_transitions_write_two_events_and_two_outbox_rows(db_url):
    _store(db_url).create_candidate(_item())
    store = _store(db_url)
    store.transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.CONFIRMED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    store.transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.DEPRECATED,
        actor="user-1",
        now="2026-07-03T02:00:00Z",
    )
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        events = s.scalars(
            select(V2MemoryEvent)
            .where(V2MemoryEvent.memory_item_id == "mem-1")
            .order_by(V2MemoryEvent.id)
        ).all()
        outbox = s.scalars(
            select(V2MemoryOutbox).where(V2MemoryOutbox.memory_item_id == "mem-1")
        ).all()
        assert len(events) == 2
        assert len(outbox) == 2
        assert [e.to_status for e in events] == ["confirmed", "deprecated"]
