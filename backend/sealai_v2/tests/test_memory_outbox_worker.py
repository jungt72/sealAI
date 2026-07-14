"""Qdrant outbox sync worker (Patch 5) — tested against a FAKE Qdrant client (no network), including
a simulated Qdrant outage (the exact scenario the retry/backoff logic exists for).

Patch 9 reconciliation: the outage-retry tests below use hourly-spaced ``now`` timestamps, which
happens to already exceed the real time-windowed backoff (base 30s, doubling, capped at 1h) between
every pair of passes — so their pass-by-pass assertions are unchanged by the backoff upgrade. A new
test below (``test_backoff_window_blocks_an_immediate_retry_pass``) exercises the actual backoff
window directly, since none of the pre-existing tests otherwise would."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from sealai_v2.config import settings as settings_module
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
from sealai_v2.memory import outbox_worker as outbox_worker_module
from sealai_v2.memory.outbox_worker import (
    drain_outbox,
    ensure_memory_collection,
    outbox_health,
)
from sealai_v2.security.cost_control import (
    CostControlPolicy,
    EmbeddingServiceAdmission,
    InMemoryCostControlStore,
    REMOTE_EMBEDDING_MAX_INPUT_BYTES,
)

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
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts):
        batch = tuple(texts)
        self.calls.append(batch)
        return [_ListLike([0.1, 0.2, 0.3]) for _ in batch]


class _FailingEmbedder(_FakeEmbedder):
    def embed(self, texts):
        batch = tuple(texts)
        self.calls.append(batch)
        raise ConnectionError("single embedding attempt failed")


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.upserted: list[tuple[str, list]] = []
        self.deleted: list[tuple[str, list]] = []

    def upsert(self, collection: str, points):
        self.upserted.append((collection, list(points)))

    def delete(self, collection: str, points_selector):
        self.deleted.append((collection, list(points_selector)))


class _AlwaysFailingQdrantClient:
    """Models a Qdrant outage — every upsert raises, the exact scenario the retry/attempt-cap
    logic exists for."""

    def upsert(self, collection: str, points):
        raise ConnectionError(
            "RAW-DOCUMENT-CANARY url=https://qdrant.invalid/items?doc=42 "
            "auth=AUTH-METADATA-CANARY"
        )


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


def _service_gate(store: InMemoryCostControlStore) -> EmbeddingServiceAdmission:
    return EmbeddingServiceAdmission(
        store,
        CostControlPolicy(
            subject_per_minute=100,
            tenant_per_minute=100,
            subject_per_day=100,
            tenant_per_day=100,
            tenant_per_month=1000,
            subject_max_concurrent=100,
            tenant_max_concurrent=100,
            lease_s=60,
            reservation_micros=100,
            daily_budget_micros=10_000,
            monthly_budget_micros=100_000,
        ),
        service="memory_outbox",
    )


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


def test_remote_memory_batch_uses_one_shared_non_refundable_admission(db_url):
    _store(db_url).create_candidate(_item())
    _store(db_url).create_candidate(
        _item(id="mem-2", semantic_key="pref:units:imperial", content="uses inches")
    )
    sm = make_sessionmaker(make_engine(db_url))
    cost_store = InMemoryCostControlStore()
    embedder = _FakeEmbedder()

    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=embedder,
        now="2026-07-03T01:00:00Z",
        remote_embeddings=True,
        service_admission=_service_gate(cost_store),
    )

    assert result.claimed == result.synced == 2
    assert embedder.calls == [("prefers metric units", "uses inches")]
    summary = cost_store.summary()
    assert summary["active_requests"] == 0
    assert summary["day"]["admitted_requests"] == 1
    assert summary["day"]["reserved_cost_micros"] == 100


def test_remote_provider_failure_stops_after_one_admitted_worker_attempt(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    cost_store = InMemoryCostControlStore()
    embedder = _FailingEmbedder()

    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=embedder,
        now="2026-07-03T01:00:00Z",
        remote_embeddings=True,
        service_admission=_service_gate(cost_store),
    )

    assert result.claimed == 1 and result.synced == 0
    assert embedder.calls == [("prefers metric units",)]
    summary = cost_store.summary()
    assert summary["day"]["admitted_requests"] == 1
    assert summary["day"]["reserved_cost_micros"] == 100
    with sm() as session:
        row = session.scalar(select(V2MemoryOutbox))
        assert row.status == "pending" and row.attempts == 1
        assert row.next_attempt_at == "2026-07-03T01:00:30Z"
        assert row.last_error == "infrastructure_error:ConnectionError"


def test_remote_memory_collection_warmup_has_its_own_admission(monkeypatch):
    cost_store = InMemoryCostControlStore()
    embedder = _FakeEmbedder()
    ensured: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(
        outbox_worker_module,
        "ensure_collection",
        lambda _client, collection, dim, *, sparse: ensured.append(
            (collection, dim, sparse)
        ),
    )

    ensure_memory_collection(
        object(),
        embedder,
        collection="memory-v1",
        remote_embeddings=True,
        service_admission=_service_gate(cost_store),
    )

    assert embedder.calls == [("_warmup_",)]
    assert ensured == [("memory-v1", 3, False)]
    assert cost_store.summary()["day"]["admitted_requests"] == 1


def test_empty_remote_memory_queue_has_no_admission_or_embedding_call(db_url):
    sm = make_sessionmaker(make_engine(db_url))
    embedder = _FakeEmbedder()
    prepared: list[bool] = []

    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=embedder,
        now="2026-07-03T01:00:00Z",
        remote_embeddings=True,
        prepare_embeddings=lambda: prepared.append(True),
    )

    assert result.claimed == 0
    assert prepared == []
    assert embedder.calls == []


@pytest.mark.parametrize("content", ("", "x" * (REMOTE_EMBEDDING_MAX_INPUT_BYTES + 1)))
def test_invalid_remote_memory_payload_is_rejected_before_lazy_factory_or_admission(
    db_url, content
):
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as session:
        session.add(
            V2MemoryOutbox(
                memory_item_id="mem-invalid",
                tenant_id="tenant-a",
                event_type="upsert",
                payload={"id": "mem-invalid", "content": content},
                created_at="2026-07-03T00:00:00Z",
            )
        )
        session.commit()
    prepared: list[bool] = []
    cost_store = InMemoryCostControlStore()

    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=None,
        now="2026-07-03T01:00:00Z",
        remote_embeddings=True,
        prepare_embeddings=lambda: prepared.append(True)
        or (_FakeEmbedder(), _service_gate(cost_store)),
    )

    assert result.claimed == 1 and result.synced == 0
    assert prepared == []
    assert cost_store.summary()["day"]["admitted_requests"] == 0
    with sm() as session:
        row = session.scalar(select(V2MemoryOutbox))
        assert row.status == "pending" and row.attempts == 1
        assert row.last_error in {
            "embedding_input_empty",
            "embedding_input_bytes_exceeded",
        }


def test_remote_delete_only_memory_pass_has_no_admission_or_warmup(db_url):
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as session:
        session.add(
            V2MemoryOutbox(
                memory_item_id="mem-deleted",
                tenant_id="tenant-a",
                event_type="delete",
                payload={"id": "mem-deleted"},
                created_at="2026-07-03T00:00:00Z",
            )
        )
        session.commit()
    embedder = _FakeEmbedder()
    prepared: list[bool] = []

    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=embedder,
        now="2026-07-03T01:00:00Z",
        batch_size=51,
        max_attempts=6,
        remote_embeddings=True,
        prepare_embeddings=lambda: prepared.append(True),
    )

    assert result.claimed == result.synced == 1
    assert prepared == []
    assert embedder.calls == []


def test_remote_memory_batch_without_service_gate_fails_before_provider_io(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    embedder = _FakeEmbedder()

    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=embedder,
        now="2026-07-03T01:00:00Z",
        remote_embeddings=True,
    )

    assert result.claimed == 1 and result.synced == 0
    assert embedder.calls == []
    with sm() as session:
        row = session.scalar(select(V2MemoryOutbox))
        assert row.status == "pending"
        assert row.last_error == "provider_admission_missing"


def test_memory_cli_empty_queue_keeps_paid_gate_and_embedder_lazy(db_url, monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "Settings",
        lambda: SimpleNamespace(
            database_url=db_url,
            qdrant_url="http://qdrant",
            embed_provider="openai",
            provider_requests_enabled=False,
            outbox_max_attempts=5,
            outbox_claim_timeout_s=300,
            memory_qdrant_collection="memory-v1",
        ),
    )
    provider_factories: list[str] = []
    monkeypatch.setattr(
        outbox_worker_module,
        "_make_client",
        lambda _settings: provider_factories.append("qdrant"),
    )
    monkeypatch.setattr(
        outbox_worker_module,
        "_make_memory_embedder",
        lambda _settings: provider_factories.append("embedder"),
    )

    assert outbox_worker_module.main(["drain"]) == 0

    assert provider_factories == ["qdrant"]


def test_memory_cli_upsert_checks_kill_switch_before_remote_embedder(
    db_url, monkeypatch
):
    _store(db_url).create_candidate(_item())
    monkeypatch.setattr(
        settings_module,
        "Settings",
        lambda: SimpleNamespace(
            database_url=db_url,
            qdrant_url="http://qdrant",
            embed_provider="openai",
            provider_requests_enabled=False,
            outbox_max_attempts=5,
            outbox_claim_timeout_s=300,
            memory_qdrant_collection="memory-v1",
        ),
    )
    factories: list[str] = []
    monkeypatch.setattr(
        outbox_worker_module,
        "_make_client",
        lambda _settings: factories.append("qdrant") or _FakeQdrantClient(),
    )
    monkeypatch.setattr(
        outbox_worker_module,
        "_make_memory_embedder",
        lambda _settings: factories.append("embedder") or _FakeEmbedder(),
    )

    assert outbox_worker_module.main(["drain"]) == 1

    assert factories == ["qdrant"]
    with make_sessionmaker(make_engine(db_url))() as session:
        row = session.scalar(select(V2MemoryOutbox))
        assert row.status == "pending"
        assert row.last_error == "provider_requests_disabled"


def test_drain_targets_configured_versioned_collection(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    client = _FakeQdrantClient()

    result = drain_outbox(
        sm,
        qdrant_client=client,
        embedder=_FakeEmbedder(),
        now="2026-07-03T01:00:00Z",
        collection="sealai_v2_memory_local_minilm_v1",
    )

    assert result.synced == 1
    assert client.upserted[0][0] == "sealai_v2_memory_local_minilm_v1"


def test_drain_calls_qdrant_delete_for_a_delete_event_type_not_upsert(db_url):
    # Patch 10: memory/purge.py's reap job enqueues event_type="delete" rows — the drain must call
    # qdrant_client.delete for these, NOT re-upsert the item's last known state (the bug this test
    # guards against: before Patch 10, drain_outbox ignored event_type entirely).
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        s.add(
            V2MemoryOutbox(
                memory_item_id="mem-purged",
                tenant_id="tenant-a",
                event_type="delete",
                payload={"id": "mem-purged", "tenant_id": "tenant-a"},
                created_at="2026-07-03T00:00:00Z",
            )
        )
        s.commit()
    client = _FakeQdrantClient()
    result = drain_outbox(
        sm, qdrant_client=client, embedder=_FakeEmbedder(), now="2026-07-03T01:00:00Z"
    )
    assert result.synced == 1
    assert client.upserted == []  # never upserted
    assert len(client.deleted) == 1
    collection, point_ids = client.deleted[0]
    assert collection == "sealai_v2_memory"
    assert point_ids == ["mem-purged"]
    with sm() as s:
        row = s.scalars(select(V2MemoryOutbox)).one()
        assert row.status == "done"


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
        assert row.last_error == "infrastructure_error:ConnectionError"
        assert "RAW-DOCUMENT-CANARY" not in row.last_error
        assert "qdrant.invalid" not in row.last_error
        assert "AUTH-METADATA-CANARY" not in row.last_error


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


def test_stale_processing_lease_is_reclaimed_after_worker_restart(db_url):
    _store(db_url).create_candidate(_item())
    sm = make_sessionmaker(make_engine(db_url))
    with sm() as s:
        row = s.scalars(select(V2MemoryOutbox)).one()
        row.status = "processing"
        row.processed_at = "2026-07-03T00:00:00Z"
        s.commit()

    result = drain_outbox(
        sm,
        qdrant_client=_FakeQdrantClient(),
        embedder=_FakeEmbedder(),
        now="2026-07-03T01:00:00Z",
        claim_timeout_seconds=300,
    )
    assert result.claimed == 1
    assert result.synced == 1


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
