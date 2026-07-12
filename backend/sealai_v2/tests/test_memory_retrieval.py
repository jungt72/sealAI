"""Memory retrieval + Postgres revalidation (Patch 6) — the headline test proves the exact incident
this module exists to prevent: Qdrant still returning a point for an item that Postgres has since
marked rejected/deprecated/deleted must NEVER let that item reach the caller."""

from __future__ import annotations

import pytest

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.memory_store import InProcessMemoryStore, PostgresMemoryStore
from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from sealai_v2.memory.retrieval import revalidate, retrieve_memory


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


# --- revalidate() — pure, in-process store ---


def test_revalidate_keeps_a_confirmed_item():
    store = InProcessMemoryStore()
    store.create_candidate(_item(status=MemoryStatus.CONFIRMED))
    result = revalidate(
        ["mem-1"], tenant_id="tenant-a", store=store, now="2026-07-03T01:00:00Z"
    )
    assert len(result) == 1 and result[0].id == "mem-1"


@pytest.mark.parametrize(
    "status",
    [
        MemoryStatus.REJECTED,
        MemoryStatus.DEPRECATED,
        MemoryStatus.DELETED_PENDING_PURGE,
        MemoryStatus.PURGED,
    ],
)
def test_revalidate_drops_never_injectable_statuses(status):
    store = InProcessMemoryStore()
    store.create_candidate(_item(status=status))
    result = revalidate(
        ["mem-1"], tenant_id="tenant-a", store=store, now="2026-07-03T01:00:00Z"
    )
    assert result == ()


def test_revalidate_drops_an_id_that_does_not_exist():
    store = InProcessMemoryStore()
    result = revalidate(
        ["nope"], tenant_id="tenant-a", store=store, now="2026-07-03T01:00:00Z"
    )
    assert result == ()


def test_revalidate_drops_an_id_belonging_to_another_tenant():
    store = InProcessMemoryStore()
    store.create_candidate(_item(tenant_id="tenant-a"))
    result = revalidate(
        ["mem-1"], tenant_id="tenant-b", store=store, now="2026-07-03T01:00:00Z"
    )
    assert result == ()


def test_revalidate_drops_an_item_past_its_purge_after():
    store = InProcessMemoryStore()
    store.create_candidate(
        _item(status=MemoryStatus.CONFIRMED, purge_after="2026-07-01T00:00:00Z")
    )
    result = revalidate(
        ["mem-1"], tenant_id="tenant-a", store=store, now="2026-07-03T01:00:00Z"
    )
    assert (
        result == ()
    )  # "expired" per the source prompt's own wording, defense-in-depth


def test_revalidate_keeps_an_item_whose_purge_after_has_not_arrived_yet():
    store = InProcessMemoryStore()
    store.create_candidate(
        _item(status=MemoryStatus.CONFIRMED, purge_after="2026-12-31T00:00:00Z")
    )
    result = revalidate(
        ["mem-1"], tenant_id="tenant-a", store=store, now="2026-07-03T01:00:00Z"
    )
    assert len(result) == 1


def test_revalidate_preserves_qdrant_rank_order_among_survivors():
    store = InProcessMemoryStore()
    store.create_candidate(
        _item(id="a", status=MemoryStatus.CONFIRMED, semantic_key="k-a")
    )
    store.create_candidate(
        _item(id="b", status=MemoryStatus.CONFIRMED, semantic_key="k-b")
    )
    store.create_candidate(
        _item(id="c", status=MemoryStatus.REJECTED, semantic_key="k-c")
    )
    result = revalidate(
        ["c", "a", "b"], tenant_id="tenant-a", store=store, now="2026-07-03T01:00:00Z"
    )
    assert [it.id for it in result] == [
        "a",
        "b",
    ]  # c dropped, a/b keep Qdrant's rank order


# --- retrieve_memory() — fake Qdrant + real (sqlite) Postgres store ---


class _ListLike(list):
    def tolist(self):
        return list(self)


class _FakeEmbedder:
    def embed(self, texts):
        return [_ListLike([0.1, 0.2, 0.3]) for _ in texts]


class _FakePoint:
    def __init__(self, point_id: str) -> None:
        self.id = point_id


class _FakeQueryResult:
    def __init__(self, points) -> None:
        self.points = points


class _FakeQdrantClient:
    """Returns a FIXED point list regardless of what Postgres now says — models Qdrant genuinely
    not having caught up yet (or never catching up, if the outbox sync permanently failed)."""

    def __init__(self, point_ids: list[str]) -> None:
        self._point_ids = point_ids
        self.last_query_kwargs: dict | None = None
        self.last_collection: str | None = None

    def query_points(self, collection, **kwargs):
        self.last_collection = collection
        self.last_query_kwargs = kwargs
        return _FakeQueryResult([_FakePoint(pid) for pid in self._point_ids])


@pytest.fixture
def db_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'retrieval.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def _pg_store(url: str) -> PostgresMemoryStore:
    return PostgresMemoryStore(make_sessionmaker(make_engine(url)))


def test_stale_qdrant_result_cannot_be_injected(db_url):
    # The headline scenario: create + confirm an item (so Qdrant WOULD have indexed it as
    # confirmed at some point), then reject it in Postgres. Qdrant's fake client still returns
    # the point (simulating either sync lag or a failed outbox sync) — retrieve_memory must NOT
    # surface it regardless.
    store = _pg_store(db_url)
    store.create_candidate(_item(status=MemoryStatus.CANDIDATE))
    store.transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.REJECTED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    qdrant = _FakeQdrantClient(point_ids=["mem-1"])  # stale — still "knows about" mem-1
    result = retrieve_memory(
        "prefers metric units",
        tenant_id="tenant-a",
        qdrant_client=qdrant,
        embedder=_FakeEmbedder(),
        store=store,
        now="2026-07-03T02:00:00Z",
    )
    assert result == ()  # NOT the rejected item — Postgres, not Qdrant, decided this


def test_a_confirmed_item_that_is_actually_still_confirmed_IS_returned(db_url):
    store = _pg_store(db_url)
    store.create_candidate(_item(status=MemoryStatus.CANDIDATE))
    store.transition_status(
        tenant_id="tenant-a",
        item_id="mem-1",
        to_status=MemoryStatus.CONFIRMED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    qdrant = _FakeQdrantClient(point_ids=["mem-1"])
    result = retrieve_memory(
        "prefers metric units",
        tenant_id="tenant-a",
        qdrant_client=qdrant,
        embedder=_FakeEmbedder(),
        store=store,
        now="2026-07-03T02:00:00Z",
    )
    assert len(result) == 1 and result[0].status == MemoryStatus.CONFIRMED


def test_retrieve_memory_never_reads_qdrant_payload():
    # with_payload=False must be passed — the whole point is that Qdrant's payload is never even
    # fetched, let alone trusted, for the injectability decision (see the module docstring).
    store = InProcessMemoryStore()
    qdrant = _FakeQdrantClient(point_ids=[])
    retrieve_memory(
        "q",
        tenant_id="tenant-a",
        qdrant_client=qdrant,
        embedder=_FakeEmbedder(),
        store=store,
        now="2026-07-03T01:00:00Z",
    )
    assert qdrant.last_query_kwargs["with_payload"] is False


def test_retrieve_memory_targets_configured_versioned_collection():
    store = InProcessMemoryStore()
    qdrant = _FakeQdrantClient(point_ids=[])

    retrieve_memory(
        "q",
        tenant_id="tenant-a",
        qdrant_client=qdrant,
        embedder=_FakeEmbedder(),
        store=store,
        now="2026-07-03T01:00:00Z",
        collection="sealai_v2_memory_local_minilm_v1",
    )

    assert qdrant.last_collection == "sealai_v2_memory_local_minilm_v1"


def test_retrieve_memory_filters_qdrant_query_by_tenant_hard_filter():
    store = InProcessMemoryStore()
    qdrant = _FakeQdrantClient(point_ids=[])
    retrieve_memory(
        "q",
        tenant_id="tenant-a",
        qdrant_client=qdrant,
        embedder=_FakeEmbedder(),
        store=store,
        now="2026-07-03T01:00:00Z",
    )
    from qdrant_client.models import Filter

    assert isinstance(qdrant.last_query_kwargs["query_filter"], Filter)


def test_retrieve_memory_respects_k_after_revalidation_drops_some(db_url):
    store = _pg_store(db_url)
    for i in range(3):
        store.create_candidate(
            _item(id=f"m{i}", status=MemoryStatus.CONFIRMED, semantic_key=f"k{i}")
        )
    store.create_candidate(
        _item(id="rejected-one", status=MemoryStatus.CANDIDATE, semantic_key="k-r")
    )
    store.transition_status(
        tenant_id="tenant-a",
        item_id="rejected-one",
        to_status=MemoryStatus.REJECTED,
        actor="user-1",
        now="2026-07-03T01:00:00Z",
    )
    qdrant = _FakeQdrantClient(point_ids=["rejected-one", "m0", "m1", "m2"])
    result = retrieve_memory(
        "q",
        tenant_id="tenant-a",
        qdrant_client=qdrant,
        embedder=_FakeEmbedder(),
        store=store,
        now="2026-07-03T02:00:00Z",
        k=2,
    )
    assert (
        len(result) == 2
    )  # k respected even though the rejected one had to be dropped first
    assert all(it.status == MemoryStatus.CONFIRMED for it in result)
