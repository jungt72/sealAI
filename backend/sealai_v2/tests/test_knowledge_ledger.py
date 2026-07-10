from __future__ import annotations

from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import (
    V2KnowledgeClaim,
    V2KnowledgeDocument,
    V2KnowledgeOutbox,
    V2KnowledgeReview,
)
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    KnowledgeDocumentInput,
    KnowledgeLedgerError,
    PostgresKnowledgeLedger,
)

NOW = "2026-07-10T10:00:00Z"


def _ledger(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'knowledge.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    return PostgresKnowledgeLedger(sf), sf


def _catalog(*, text="PTFE ist chemisch bestaendig.", reviewed=False):
    status = "reviewed" if reviewed else "draft"
    claim = {
        "text": text,
        "review_state": status,
        "kind": "family_tendency",
        "sources": ["DIN EN ISO 1"] if reviewed else [],
        "provenance": ["owner:test"] if reviewed else ["paperless-draft:test"],
    }
    return FachkartenCatalog(
        cards=(
            _card(
                {
                    "id": "FK-PTFE",
                    "scope": {"material": ["PTFE"]},
                    "claims": [claim],
                    "review_state": status,
                    "provenance": claim["provenance"],
                    "version": "v1",
                }
            ),
        )
    )


def _document(content=b"source-v1"):
    return KnowledgeDocumentInput(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        source_type="paperless",
        source_id="42",
        source_uri="paperless#42:PTFE",
        object_key="paperless#42",
        title="PTFE",
        content=content,
        authority="external_unreviewed",
    )


def test_replace_catalog_is_atomic_versioned_and_idempotent(tmp_path):
    ledger, sf = _ledger(tmp_path)
    first = ledger.replace_catalog(
        _document(), _catalog(), now=NOW, actor="paperless-webhook"
    )
    second = ledger.replace_catalog(
        _document(), _catalog(), now=NOW, actor="paperless-webhook"
    )

    assert first.document_version == second.document_version == 1
    assert first.claims_created == 1 and first.outbox_enqueued == 1
    assert second.claims_created == 0 and second.outbox_enqueued == 0
    with sf() as session:
        assert len(session.scalars(select(V2KnowledgeDocument)).all()) == 1
        assert len(session.scalars(select(V2KnowledgeClaim)).all()) == 1
        assert len(session.scalars(select(V2KnowledgeOutbox)).all()) == 1


def test_changed_source_creates_revision_and_retires_old_claim(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="webhook")
    result = ledger.replace_catalog(
        _document(b"source-v2"),
        _catalog(text="PTFE zeigt ausgepraegten Kaltfluss."),
        now="2026-07-10T11:00:00Z",
        actor="webhook",
    )

    assert result.document_version == 2
    assert result.claims_created == 1 and result.claims_retired == 1
    with sf() as session:
        documents = session.scalars(
            select(V2KnowledgeDocument).order_by(V2KnowledgeDocument.version)
        ).all()
        claims = session.scalars(
            select(V2KnowledgeClaim).order_by(V2KnowledgeClaim.created_at)
        ).all()
        assert [document.version for document in documents] == [1, 2]
        assert sum(1 for claim in claims if claim.active) == 1


def test_review_is_append_only_and_postgres_controls_retrieval_status(tmp_path):
    ledger, sf = _ledger(tmp_path)
    result = ledger.replace_catalog(
        _document(), _catalog(), now=NOW, actor="paperless-webhook"
    )
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))

    try:
        ledger.review_claim(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            claim_id=claim_id,
            to_status="approved",
            actor="owner",
            now=NOW,
        )
    except KnowledgeLedgerError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("approval without evidence was accepted")

    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="approved",
        actor="owner",
        now=NOW,
        evidence=("DIN EN ISO 1, owner checked",),
    )
    resolved = ledger.resolve_claims((claim_id,), tenant_id="customer-a")
    assert resolved[claim_id]["review_state"] == "reviewed"
    assert resolved[claim_id]["document_id"] == result.document_id

    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="rejected",
        actor="owner",
        now="2026-07-10T12:00:00Z",
        note="Source does not support the scope",
    )
    assert ledger.resolve_claims((claim_id,), tenant_id="customer-a") == {}
    with sf() as session:
        reviews = session.scalars(
            select(V2KnowledgeReview).order_by(V2KnowledgeReview.id)
        ).all()
        assert [(row.from_status, row.to_status) for row in reviews] == [
            ("draft", "approved"),
            ("approved", "rejected"),
        ]


def test_automated_reingest_cannot_downgrade_reviewed_claim(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(
        _document(), _catalog(reviewed=True), now=NOW, actor="owner-bootstrap"
    )
    ledger.replace_catalog(
        _document(), _catalog(reviewed=False), now=NOW, actor="paperless-webhook"
    )
    with sf() as session:
        row = session.scalar(select(V2KnowledgeClaim))
        assert row.review_status == "approved"
