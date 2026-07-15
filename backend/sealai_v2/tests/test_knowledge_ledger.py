from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import (
    V2GovernanceDecision,
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
from sealai_v2.tests.affiliation_fixtures import affiliation, persist_affiliations

NOW = "2026-07-10T10:00:00Z"


def _ledger(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'knowledge.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    persist_affiliations(
        sf,
        affiliation("domain-reviewer:alice", "reviewer-org"),
        affiliation("domain-approver:bob", "approver-org"),
    )
    return PostgresKnowledgeLedger(sf), sf


def _catalog(
    *,
    text="PTFE ist chemisch bestaendig.",
    reviewed=False,
    with_source=True,
    source="DIN EN ISO 1",
):
    status = "reviewed" if reviewed else "draft"
    claim = {
        "text": text,
        "review_state": status,
        "kind": "family_tendency",
        "sources": [source] if with_source else [],
        "provenance": ["owner:test"] if reviewed else ["paperless-draft:test"],
    }
    if reviewed:
        claim.update(
            {
                "reviewed_by": "domain-reviewer:alice",
                "reviewed_at": NOW,
                "review_expires_at": "2099-07-10T10:00:00Z",
            }
        )
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


def _review_and_approve(
    ledger,
    claim_id: str,
    *,
    reviewer: str = "domain-reviewer:alice",
    approver: str = "domain-approver:bob",
    now: str = NOW,
    evidence=("DIN EN ISO 1",),
    applicability=None,
    uncertainty: str = "conditional",
    transferability: str = "family_level_orientation",
    review_expires_at: str = "2099-07-10T10:00:00Z",
    change_reason: str = "independent domain review",
):
    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="reviewed",
        actor=reviewer,
        actor_roles=("knowledge_reviewer",),
        now=now,
        evidence=evidence,
        applicability=applicability or {"material": ["PTFE"]},
        uncertainty=uncertainty,
        transferability=transferability,
        review_expires_at=review_expires_at,
        change_reason=change_reason,
    )
    return ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="approved",
        actor=approver,
        actor_roles=("knowledge_approver",),
        now=now,
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


def test_quarantined_catalog_reimport_is_idempotent(tmp_path):
    ledger, _ = _ledger(tmp_path)
    catalog = _catalog(reviewed=True, with_source=False)
    first = ledger.replace_catalog(
        _document(), catalog, now=NOW, actor="release-bootstrap"
    )
    second = ledger.replace_catalog(
        _document(),
        catalog,
        now="2026-07-10T11:00:00Z",
        actor="release-bootstrap",
    )

    assert first.claims_created == 1
    assert second.claims_created == 0
    assert second.claims_updated == 0
    assert second.claims_retired == 0
    assert second.outbox_enqueued == 0


def test_claim_identity_survives_unrelated_document_revision(tmp_path):
    ledger, sf = _ledger(tmp_path)
    first = ledger.replace_catalog(
        _document(), _catalog(), now=NOW, actor="paperless-webhook"
    )
    with sf() as session:
        first_id = session.scalar(select(V2KnowledgeClaim.id))

    second = ledger.replace_catalog(
        _document(b"source-v2"),
        _catalog(),
        now="2026-07-10T11:00:00Z",
        actor="paperless-webhook",
    )

    assert first.document_id != second.document_id
    assert second.claims_created == 0
    assert second.claims_retired == 0
    assert second.claims_updated == 1
    with sf() as session:
        claims = session.scalars(select(V2KnowledgeClaim)).all()
        assert len(claims) == 1
        assert claims[0].id == first_id
        assert claims[0].document_id == second.document_id
        assert len(claims[0].authority_fingerprint) == 64


def test_duplicate_logical_claim_identity_is_rejected(tmp_path):
    ledger, _ = _ledger(tmp_path)
    catalog = _catalog()
    card = catalog.cards[0]
    duplicate = FachkartenCatalog(
        cards=(replace(card, claims=(card.claims[0], card.claims[0])),)
    )

    with pytest.raises(KnowledgeLedgerError, match="duplicate logical claim identity"):
        ledger.replace_catalog(_document(), duplicate, now=NOW, actor="webhook")


def test_human_review_survives_unchanged_claim_contract_revision(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="webhook")
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))
    _review_and_approve(ledger, claim_id)

    second = ledger.replace_catalog(
        _document(b"source-v2"),
        _catalog(),
        now="2026-07-10T11:00:00Z",
        actor="release-bootstrap",
    )

    with sf() as session:
        row = session.get(V2KnowledgeClaim, claim_id)
        reviews = session.scalars(
            select(V2KnowledgeReview).order_by(V2KnowledgeReview.id)
        ).all()
        decisions = session.scalars(
            select(V2GovernanceDecision).order_by(V2GovernanceDecision.resource_version)
        ).all()
        assert row.review_status == "approved"
        assert row.review_origin == "human_api"
        assert row.reviewed_by == "domain-reviewer:alice"
        assert row.document_id == second.document_id
        assert [(item.from_status, item.to_status) for item in reviews] == [
            ("draft", "reviewed"),
            ("reviewed", "approved"),
        ]
        assert [(item.resource_version, item.reason_code) for item in decisions] == [
            (3, "no_shared_affiliation"),
            (4, "unchanged_authority_contract_carry_forward"),
        ]
    assert claim_id in ledger.resolve_claims((claim_id,), tenant_id="customer-a")


def test_authority_contract_change_quarantines_prior_human_review(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="webhook")
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))
    _review_and_approve(ledger, claim_id)

    ledger.replace_catalog(
        _document(b"source-v2"),
        _catalog(source="DIN EN ISO 2"),
        now="2026-07-10T11:00:00Z",
        actor="release-bootstrap",
    )

    with sf() as session:
        row = session.get(V2KnowledgeClaim, claim_id)
        reviews = session.scalars(
            select(V2KnowledgeReview).order_by(V2KnowledgeReview.id)
        ).all()
        assert row.review_status == "quarantined"
        assert row.review_origin == "policy_import"
        assert row.sources_json == ["DIN EN ISO 2"]
        assert reviews[-1].from_status == "approved"
        assert reviews[-1].to_status == "quarantined"
        assert "Authority contract changed" in reviews[-1].note
    assert ledger.resolve_claims((claim_id,), tenant_id="customer-a") == {}


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

    with pytest.raises(KnowledgeLedgerError, match="authenticated human actor"):
        ledger.review_claim(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            claim_id=claim_id,
            to_status="rejected",
            actor="release-bootstrap",
            now=NOW,
        )

    try:
        ledger.review_claim(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            claim_id=claim_id,
            to_status="approved",
            actor="owner",
            now=NOW,
        )
    except KnowledgeLedgerError as exc:
        assert "completed independent review" in str(exc)
    else:
        raise AssertionError("approval without evidence was accepted")

    with pytest.raises(KnowledgeLedgerError, match="expiry"):
        ledger.review_claim(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            claim_id=claim_id,
            to_status="reviewed",
            actor="domain-reviewer:alice",
            now=NOW,
            evidence=("DIN EN ISO 1, owner checked",),
            applicability={"material": ["PTFE"]},
            uncertainty="conditional",
            transferability="family_level_orientation",
            review_expires_at="not-a-date",
        )

    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="reviewed",
        actor="domain-reviewer:alice",
        actor_roles=("knowledge_reviewer",),
        now=NOW,
        evidence=("DIN EN ISO 1, reviewer checked",),
        applicability={"material": ["PTFE"]},
        uncertainty="conditional",
        transferability="family_level_orientation",
        review_expires_at="2099-07-10T10:00:00Z",
    )
    with pytest.raises(KnowledgeLedgerError, match="different human actors"):
        ledger.review_claim(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            claim_id=claim_id,
            to_status="approved",
            actor="domain-reviewer:alice",
            actor_roles=("knowledge_approver",),
            now=NOW,
        )

    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="quarantined",
        actor="domain-reviewer:carol",
        now=NOW,
        note="reset after independence test",
    )

    _review_and_approve(
        ledger,
        claim_id,
        evidence=("DIN EN ISO 1, reviewer checked",),
        change_reason="independent review",
    )
    resolved = ledger.resolve_claims((claim_id,), tenant_id="customer-a")
    assert resolved[claim_id]["review_state"] == "reviewed"
    assert resolved[claim_id]["document_id"] == result.document_id
    assert resolved[claim_id]["evidence"][0]["citation"]
    assert resolved[claim_id]["applicability"] == {"material": ["PTFE"]}
    assert resolved[claim_id]["uncertainty"] == "conditional"
    assert resolved[claim_id]["review_expires_at"] == "2099-07-10T10:00:00Z"
    assert resolved[claim_id]["reviewed_by"] == "domain-reviewer:alice"

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
            ("draft", "reviewed"),
            ("reviewed", "quarantined"),
            ("quarantined", "reviewed"),
            ("reviewed", "approved"),
            ("approved", "rejected"),
        ]


def test_expired_approved_claim_is_not_resolved(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="webhook")
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))
    _review_and_approve(ledger, claim_id)
    with sf() as session:
        row = session.get(V2KnowledgeClaim, claim_id)
        row.review_expires_at = "2020-01-01T00:00:00Z"
        session.commit()

    assert ledger.resolve_claims((claim_id,), tenant_id="customer-a") == {}


def test_human_api_approval_without_server_coi_decision_is_not_resolved(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="webhook")
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))
    _review_and_approve(ledger, claim_id)
    with sf() as session:
        session.query(V2GovernanceDecision).delete()
        session.commit()

    assert ledger.resolve_claims((claim_id,), tenant_id="customer-a") == {}


def test_human_api_approval_with_stale_server_decision_is_not_resolved(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="webhook")
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))
    _review_and_approve(ledger, claim_id)
    with sf() as session:
        decision = session.scalar(select(V2GovernanceDecision))
        assert decision is not None
        decision.resource_version -= 1
        session.commit()

    assert ledger.resolve_claims((claim_id,), tenant_id="customer-a") == {}


def test_human_api_approval_with_mismatched_contract_binding_is_not_resolved(
    tmp_path,
):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="webhook")
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))
    _review_and_approve(ledger, claim_id)
    with sf() as session:
        row = session.get(V2KnowledgeClaim, claim_id)
        assert row is not None
        row.authority_fingerprint = "0" * 64
        session.commit()

    assert ledger.resolve_claims((claim_id,), tenant_id="customer-a") == {}


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


def test_declared_reviewed_claim_without_source_is_quarantined(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(
        _document(),
        _catalog(reviewed=True, with_source=False),
        now=NOW,
        actor="owner-bootstrap",
    )

    with sf() as session:
        row = session.scalar(select(V2KnowledgeClaim))
        assert row.review_status == "quarantined"
        assert row.evidence_json == []
        claim_id = row.id
        review = session.scalar(select(V2KnowledgeReview))
        assert review.to_status == "quarantined"
    assert ledger.resolve_claims((claim_id,), tenant_id="customer-a") == {}


def test_evidence_removal_quarantines_previously_approved_claim(tmp_path):
    ledger, sf = _ledger(tmp_path)
    ledger.replace_catalog(
        _document(), _catalog(reviewed=True), now=NOW, actor="owner-bootstrap"
    )
    ledger.replace_catalog(
        _document(),
        _catalog(reviewed=True, with_source=False),
        now="2026-07-10T11:00:00Z",
        actor="policy-reconciliation",
    )

    with sf() as session:
        row = session.scalar(select(V2KnowledgeClaim))
        assert row.review_status == "quarantined"
        reviews = session.scalars(
            select(V2KnowledgeReview).order_by(V2KnowledgeReview.id)
        ).all()
        assert [(item.from_status, item.to_status) for item in reviews] == [
            ("unreviewed", "approved"),
            ("approved", "quarantined"),
        ]
        events = session.scalars(
            select(V2KnowledgeOutbox).order_by(V2KnowledgeOutbox.id)
        ).all()
        assert [item.event_type for item in events] == ["upsert", "delete"]
