"""PostgresMemoryStore — restart-survival + tenant isolation (mirrors test_persistence_store.py's
pattern against the sqlite-backed adapter; same dialect-agnostic SQL runs against Postgres in prod)."""

from __future__ import annotations

import pytest

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.memory_store import PostgresMemoryStore
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
