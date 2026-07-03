"""sealingAI Memory Architecture V1.0, Patch 2 — schema-only tests. No repository/CRUD class exists
yet (that's a later patch); these tests prove the 4 new tables exist with the right columns/indices
and are directly usable at the raw SQLAlchemy level, mirroring how ``db/migrate.py`` itself verifies
schema creation (``sorted(inspect(engine).get_table_names())``)."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import (
    V2MemoryEvent,
    V2MemoryItem,
    V2MemoryOutbox,
    V2MemorySource,
)

_NEW_TABLES = {
    "v2_memory_items",
    "v2_memory_sources",
    "v2_memory_events",
    "v2_memory_outbox",
}


@pytest.fixture
def db_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'memory_v2.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def test_all_four_new_tables_are_created(db_url):
    engine = make_engine(db_url)
    present = set(inspect(engine).get_table_names())
    assert _NEW_TABLES <= present


def test_new_tables_are_registered_on_base_metadata():
    # Same assertion migrate.py's up()/down() rely on (Base.metadata.tables) — a table class that
    # exists in models.py but was never imported anywhere wouldn't register here.
    assert _NEW_TABLES <= set(Base.metadata.tables)


@pytest.mark.parametrize(
    "column",
    ["tenant_id", "project_id", "case_id", "status", "semantic_key"],
)
def test_memory_items_has_every_indexed_column_the_patch_requires(db_url, column):
    engine = make_engine(db_url)
    cols = {c["name"] for c in inspect(engine).get_columns("v2_memory_items")}
    assert column in cols


@pytest.mark.parametrize(
    "column", ["version", "qdrant_sync_state", "deleted_at", "purge_after"]
)
def test_memory_items_has_every_lifecycle_column_the_patch_requires(db_url, column):
    engine = make_engine(db_url)
    cols = {c["name"] for c in inspect(engine).get_columns("v2_memory_items")}
    assert column in cols


def test_memory_items_indices_actually_exist_not_just_columns(db_url):
    engine = make_engine(db_url)
    indexed_columns: set[str] = set()
    for idx in inspect(engine).get_indexes("v2_memory_items"):
        indexed_columns.update(idx["column_names"])
    for expected in ("tenant_id", "project_id", "case_id", "status", "semantic_key"):
        assert expected in indexed_columns, f"{expected} has no index"


def test_memory_item_insert_and_query_roundtrip(db_url):
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        s.add(
            V2MemoryItem(
                id="mem-1",
                tenant_id="tenant-a",
                scope="session",
                scope_id="session-1",
                type="preference",
                status="candidate",
                content="prefers metric units",
                semantic_key="pref:units:metric",
                created_at="2026-07-03T00:00:00Z",
                updated_at="2026-07-03T00:00:00Z",
            )
        )
        s.commit()
    with sm() as s:
        row = s.execute(
            select(V2MemoryItem).where(V2MemoryItem.id == "mem-1")
        ).scalar_one()
        assert row.tenant_id == "tenant-a"
        assert row.status == "candidate"
        assert row.version == 1  # default
        assert row.qdrant_sync_state == "pending"  # default
        assert row.deleted_at is None and row.purge_after is None


def test_memory_item_case_and_project_denormalized_columns_are_independently_nullable(
    db_url,
):
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        s.add(
            V2MemoryItem(
                id="mem-case",
                tenant_id="tenant-a",
                scope="case",
                scope_id="case-42",
                case_id="case-42",  # denormalized read-path column, set to match scope_id here
                type="case_parameter",
                status="confirmed",
                content="medium: hydraulic fluid",
                semantic_key="case:case-42:medium",
                created_at="2026-07-03T00:00:00Z",
                updated_at="2026-07-03T00:00:00Z",
            )
        )
        s.commit()
    with sm() as s:
        row = s.execute(
            select(V2MemoryItem).where(V2MemoryItem.id == "mem-case")
        ).scalar_one()
        assert row.case_id == "case-42"
        assert row.project_id is None  # not populated for a case-scoped item


def test_memory_source_one_to_many_against_memory_item(db_url):
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        s.add(
            V2MemoryItem(
                id="mem-2",
                tenant_id="tenant-a",
                scope="user",
                scope_id="user-1",
                type="preference",
                status="candidate",
                content="prefers dark mode",
                semantic_key="pref:ui:theme",
                created_at="2026-07-03T00:00:00Z",
                updated_at="2026-07-03T00:00:00Z",
            )
        )
        s.add_all(
            [
                V2MemorySource(
                    memory_item_id="mem-2",
                    kind="user_stated",
                    session_id="s1",
                    created_at="2026-07-03T00:00:00Z",
                ),
                V2MemorySource(
                    memory_item_id="mem-2",
                    kind="user_stated",
                    session_id="s2",
                    created_at="2026-07-03T00:01:00Z",
                ),
            ]
        )
        s.commit()
    with sm() as s:
        rows = (
            s.execute(
                select(V2MemorySource).where(V2MemorySource.memory_item_id == "mem-2")
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2


def test_memory_event_records_a_status_transition(db_url):
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        s.add(
            V2MemoryEvent(
                memory_item_id="mem-1",
                tenant_id="tenant-a",
                event_type="confirmed",
                from_status="candidate",
                to_status="confirmed",
                actor="user-1",
                created_at="2026-07-03T00:00:00Z",
            )
        )
        s.commit()
    with sm() as s:
        row = s.execute(
            select(V2MemoryEvent).where(V2MemoryEvent.memory_item_id == "mem-1")
        ).scalar_one()
        assert row.from_status == "candidate" and row.to_status == "confirmed"


def test_memory_outbox_defaults_to_pending_with_zero_attempts(db_url):
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        s.add(
            V2MemoryOutbox(
                memory_item_id="mem-1",
                tenant_id="tenant-a",
                operation="upsert",
                created_at="2026-07-03T00:00:00Z",
            )
        )
        s.commit()
    with sm() as s:
        row = s.execute(
            select(V2MemoryOutbox).where(V2MemoryOutbox.memory_item_id == "mem-1")
        ).scalar_one()
        assert row.status == "pending"
        assert row.attempts == 0
        assert row.processed_at is None


def test_migrate_up_reports_all_four_new_tables(tmp_path):
    from sealai_v2.db.migrate import up

    url = f"sqlite:///{tmp_path / 'migrate_v2.db'}"
    engine = make_engine(url)
    remaining = up(engine)
    assert _NEW_TABLES <= set(remaining)
