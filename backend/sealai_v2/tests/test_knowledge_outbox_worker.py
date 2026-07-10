from __future__ import annotations

from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import V2KnowledgeClaim, V2KnowledgeOutbox
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    KnowledgeDocumentInput,
    PostgresKnowledgeLedger,
)
from sealai_v2.knowledge.outbox_worker import drain_knowledge_outbox

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


def test_outbox_failure_is_retried_with_backoff_without_losing_row(tmp_path):
    sf = _store(tmp_path)
    result = drain_knowledge_outbox(
        sf,
        qdrant_client=_Qdrant(error=RuntimeError("qdrant down")),
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
        assert "incomplete dense batch" in row.last_error
