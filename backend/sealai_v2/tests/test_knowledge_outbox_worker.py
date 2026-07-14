from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.config import settings as settings_module
from sealai_v2.knowledge import outbox_worker as outbox_worker_module
from sealai_v2.knowledge import qdrant_retrieval as qdrant_retrieval_module
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import V2KnowledgeClaim, V2KnowledgeOutbox
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    KnowledgeDocumentInput,
    PostgresKnowledgeLedger,
)
from sealai_v2.knowledge.outbox_worker import (
    drain_knowledge_outbox,
    ensure_knowledge_collection,
)
from sealai_v2.security.cost_control import (
    CostControlPolicy,
    EmbeddingServiceAdmission,
    InMemoryCostControlStore,
    REMOTE_EMBEDDING_MAX_INPUT_BYTES,
)

NOW = "2026-07-10T10:00:00Z"


class _Vector:
    def __init__(self, value):
        self._value = value

    def tolist(self):
        return self._value


class _Embedder:
    def __init__(self):
        self.calls = []

    def embed(self, texts):
        texts = list(texts)
        self.calls.append(texts)
        return [_Vector([0.1, 0.2, 0.3]) for _ in texts]


class _IncompleteEmbedder(_Embedder):
    def embed(self, texts):
        super().embed(texts)
        return []


class _FailingSparseEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts):
        batch = list(texts)
        self.calls.append(batch)
        raise RuntimeError("LOCAL-SPARSE-CANARY contains document text")


class _Qdrant:
    def __init__(self, *, error=None):
        self.error = error
        self.upserts = []
        self.deletes = []

    def upsert(self, collection, *, points, wait=False):
        if self.error:
            raise self.error
        assert wait is True
        self.upserts.append((collection, points))

    def delete(self, collection, *, points_selector, wait=False):
        if self.error:
            raise self.error
        assert wait is True
        self.deletes.append((collection, points_selector))


def _store(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'outbox.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    ledger = PostgresKnowledgeLedger(sf)
    catalog = FachkartenCatalog(
        cards=(
            _card(
                {
                    "id": "FK-OUTBOX",
                    "scope": {"material": ["PTFE"]},
                    "claims": [
                        {
                            "text": "PTFE ist chemisch bestaendig.",
                            "review_state": "draft",
                            "provenance": ["paperless-draft:test"],
                        }
                    ],
                    "review_state": "draft",
                    "provenance": ["paperless-draft:test"],
                }
            ),
        )
    )
    ledger.replace_catalog(
        KnowledgeDocumentInput(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            source_type="paperless",
            source_id="9",
            source_uri="paperless#9",
            object_key="paperless#9",
            title="PTFE",
            content=b"source",
            authority="external_unreviewed",
        ),
        catalog,
        now=NOW,
        actor="webhook",
    )
    return sf


def _empty_store(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'empty-outbox.db'}")
    Base.metadata.create_all(engine)
    return make_sessionmaker(engine)


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
        service="knowledge_outbox",
    )


def test_outbox_batches_embeddings_and_marks_exact_claim_version_synced(tmp_path):
    sf = _store(tmp_path)
    qdrant = _Qdrant()
    embedder = _Embedder()
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=qdrant,
        embedder=embedder,
        collection="knowledge-v1",
        passage_prefix="passage: ",
        now=NOW,
    )

    assert result.claimed == result.synced == 1
    assert embedder.calls == [["passage: PTFE ist chemisch bestaendig."]]
    point = qdrant.upserts[0][1][0]
    assert point.payload["claim_id"] == str(point.id)
    assert point.payload["review_state"] == "draft"
    with sf() as session:
        claim = session.scalar(select(V2KnowledgeClaim))
        outbox = session.scalar(select(V2KnowledgeOutbox))
        assert claim.qdrant_sync_state == "synced"
        assert claim.qdrant_synced_version == claim.version
        assert outbox.status == "done"


def test_remote_knowledge_batch_uses_shared_non_refundable_admission(tmp_path):
    sf = _store(tmp_path)
    cost_store = InMemoryCostControlStore()
    embedder = _Embedder()
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(),
        embedder=embedder,
        collection="knowledge-v1",
        passage_prefix="passage: ",
        now=NOW,
        remote_embeddings=True,
        service_admission=_service_gate(cost_store),
    )

    assert result.claimed == result.synced == 1
    assert embedder.calls == [["passage: PTFE ist chemisch bestaendig."]]
    summary = cost_store.summary()
    assert summary["active_requests"] == 0
    assert summary["day"]["admitted_requests"] == 1
    assert summary["day"]["reserved_cost_micros"] == 100


def test_remote_knowledge_collection_warmup_has_its_own_admission(monkeypatch):
    cost_store = InMemoryCostControlStore()
    embedder = _Embedder()
    ensured: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(
        outbox_worker_module,
        "ensure_collection",
        lambda _client, collection, dim, *, sparse: ensured.append(
            (collection, dim, sparse)
        ),
    )

    class _Settings:
        qdrant_collection = "knowledge-v1"
        qdrant_hybrid_enabled = False

    ensure_knowledge_collection(
        object(),
        _Settings(),
        embedder,
        remote_embeddings=True,
        service_admission=_service_gate(cost_store),
    )

    assert embedder.calls == [["_warmup_"]]
    assert ensured == [("knowledge-v1", 3, False)]
    assert cost_store.summary()["day"]["admitted_requests"] == 1


def test_empty_remote_knowledge_queue_has_no_admission_or_warmup(tmp_path):
    sf = _empty_store(tmp_path)
    embedder = _Embedder()
    prepared: list[bool] = []
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(),
        embedder=embedder,
        collection="knowledge-v1",
        passage_prefix="",
        now=NOW,
        remote_embeddings=True,
        prepare_embeddings=lambda: prepared.append(True),
    )

    assert result.claimed == 0
    assert prepared == []
    assert embedder.calls == []


def test_oversize_remote_knowledge_payload_preflights_before_factory_or_admission(
    tmp_path,
):
    sf = _store(tmp_path)
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        payload = dict(row.payload)
        payload["claim_text"] = "x" * (REMOTE_EMBEDDING_MAX_INPUT_BYTES + 1)
        row.payload = payload
        session.commit()
    prepared: list[bool] = []
    cost_store = InMemoryCostControlStore()
    qdrant = _Qdrant()

    result = drain_knowledge_outbox(
        sf,
        qdrant_client=qdrant,
        embedder=None,
        collection="knowledge-v1",
        passage_prefix="",
        now=NOW,
        remote_embeddings=True,
        prepare_embeddings=lambda: prepared.append(True)
        or (_Embedder(), _service_gate(cost_store)),
    )

    assert result.claimed == 1 and result.synced == 0
    assert prepared == []
    assert qdrant.upserts == []
    assert cost_store.summary()["day"]["admitted_requests"] == 0
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        assert row.status == "pending" and row.attempts == 1
        assert row.last_error == "embedding_input_bytes_exceeded"


def test_local_sparse_failure_precedes_paid_factory_warmup_and_admission(tmp_path):
    sf = _store(tmp_path)
    prepared: list[bool] = []
    cost_store = InMemoryCostControlStore()
    sparse = _FailingSparseEmbedder()

    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(),
        embedder=None,
        sparse_embedder=sparse,
        collection="knowledge-v1",
        passage_prefix="",
        now=NOW,
        remote_embeddings=True,
        prepare_embeddings=lambda: prepared.append(True)
        or (_Embedder(), _service_gate(cost_store)),
    )

    assert result.claimed == 1 and result.synced == 0
    assert sparse.calls == [["PTFE ist chemisch bestaendig."]]
    assert prepared == []
    assert cost_store.summary()["day"]["admitted_requests"] == 0
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        assert row.last_error == "infrastructure_error:RuntimeError"
        assert "LOCAL-SPARSE-CANARY" not in row.last_error


def test_remote_delete_only_knowledge_pass_has_no_admission_or_warmup(tmp_path):
    sf = _store(tmp_path)
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        row.event_type = "delete"
        session.commit()
    embedder = _Embedder()
    prepared: list[bool] = []
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(),
        embedder=embedder,
        collection="knowledge-v1",
        passage_prefix="",
        now=NOW,
        batch_size=51,
        max_attempts=6,
        remote_embeddings=True,
        prepare_embeddings=lambda: prepared.append(True),
    )

    assert result.claimed == result.synced == 1
    assert prepared == []
    assert embedder.calls == []


def test_remote_knowledge_batch_without_service_gate_fails_before_provider_io(
    tmp_path,
):
    sf = _store(tmp_path)
    embedder = _Embedder()
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(),
        embedder=embedder,
        collection="knowledge-v1",
        passage_prefix="",
        now=NOW,
        remote_embeddings=True,
    )

    assert result.claimed == 1 and result.synced == 0
    assert embedder.calls == []
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        assert row.status == "pending"
        assert row.last_error == "provider_admission_missing"


def test_knowledge_cli_empty_queue_keeps_paid_gate_and_embedder_lazy(
    tmp_path, monkeypatch
):
    sf = _empty_store(tmp_path)
    database_url = str(sf.kw["bind"].url)
    monkeypatch.setattr(
        settings_module,
        "Settings",
        lambda: SimpleNamespace(
            database_url=database_url,
            qdrant_url="http://qdrant",
            embed_provider="openai",
            provider_requests_enabled=False,
            outbox_max_attempts=5,
            outbox_claim_timeout_s=300,
            qdrant_hybrid_enabled=False,
            qdrant_collection="knowledge-v1",
            embed_passage_prefix="",
        ),
    )
    provider_factories: list[str] = []
    monkeypatch.setattr(
        qdrant_retrieval_module,
        "_make_client",
        lambda _settings: provider_factories.append("qdrant"),
    )
    monkeypatch.setattr(
        qdrant_retrieval_module,
        "_make_embedder",
        lambda _settings, **_kwargs: provider_factories.append("embedder"),
    )

    assert outbox_worker_module.main(["drain"]) == 0

    assert provider_factories == ["qdrant"]


def test_knowledge_cli_upsert_checks_kill_switch_before_remote_embedder(
    tmp_path, monkeypatch
):
    sf = _store(tmp_path)
    database_url = str(sf.kw["bind"].url)
    monkeypatch.setattr(
        settings_module,
        "Settings",
        lambda: SimpleNamespace(
            database_url=database_url,
            qdrant_url="http://qdrant",
            embed_provider="openai",
            provider_requests_enabled=False,
            outbox_max_attempts=5,
            outbox_claim_timeout_s=300,
            qdrant_hybrid_enabled=False,
            qdrant_collection="knowledge-v1",
            embed_passage_prefix="",
        ),
    )
    factories: list[str] = []
    monkeypatch.setattr(
        qdrant_retrieval_module,
        "_make_client",
        lambda _settings: factories.append("qdrant") or _Qdrant(),
    )
    monkeypatch.setattr(
        qdrant_retrieval_module,
        "_make_embedder",
        lambda _settings, **_kwargs: factories.append("embedder") or _Embedder(),
    )

    assert outbox_worker_module.main(["drain"]) == 1

    assert factories == ["qdrant"]
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        assert row.status == "pending"
        assert row.last_error == "provider_requests_disabled"


def test_outbox_failure_is_retried_with_backoff_without_losing_row(tmp_path):
    sf = _store(tmp_path)
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(
            error=RuntimeError(
                "RAW-DOCUMENT-CANARY url=https://qdrant.invalid/?doc=42 "
                "auth=AUTH-METADATA-CANARY"
            )
        ),
        embedder=_Embedder(),
        collection="knowledge-v1",
        passage_prefix="",
        now=NOW,
        max_attempts=3,
    )

    assert result.claimed == 1 and result.synced == 0
    assert result.failed_permanently == 0
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        assert row.status == "pending" and row.attempts == 1
        assert row.next_attempt_at == "2026-07-10T10:00:30Z"
        assert row.last_error == "infrastructure_error:RuntimeError"
        assert "RAW-DOCUMENT-CANARY" not in row.last_error
        assert "qdrant.invalid" not in row.last_error
        assert "AUTH-METADATA-CANARY" not in row.last_error


def test_incomplete_embedding_batch_is_never_marked_done(tmp_path):
    sf = _store(tmp_path)
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(),
        embedder=_IncompleteEmbedder(),
        collection="knowledge-v1",
        passage_prefix="",
        now=NOW,
    )
    assert result.synced == 0
    with sf() as session:
        row = session.scalar(select(V2KnowledgeOutbox))
        assert row.status == "pending"
        assert row.last_error == "embedding_response_incomplete"
