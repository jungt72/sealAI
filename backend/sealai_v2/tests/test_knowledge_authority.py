from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import V2KnowledgeClaim, V2KnowledgeOutbox
from sealai_v2.knowledge.authority import (
    KnowledgeAuthorityChanged,
    PostgresKnowledgeAuthority,
    RequestAuthorityGuard,
)
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    KnowledgeDocumentInput,
    PostgresKnowledgeLedger,
)

NOW = "2026-07-15T10:00:00Z"
EXPIRY = "2026-07-16T10:00:00Z"


def _catalog(text: str = "PTFE requires application-specific assessment."):
    return FachkartenCatalog(
        cards=(
            _card(
                {
                    "id": "FK-AUTHORITY",
                    "scope": {"material": ["PTFE"]},
                    "claims": [
                        {
                            "text": text,
                            "review_state": "draft",
                            "provenance": ["research:draft"],
                        }
                    ],
                    "review_state": "draft",
                    "provenance": ["research:draft"],
                }
            ),
        )
    )


def _document(content: bytes = b"authority-v1") -> KnowledgeDocumentInput:
    return KnowledgeDocumentInput(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        source_type="authority_fixture",
        source_id="1",
        source_uri="fixture:authority",
        object_key="fixture:authority",
        title="Authority fixture",
        content=content,
        authority="unreviewed",
    )


def _fixture(tmp_path, *, clock=None):
    engine = make_engine(f"sqlite:///{tmp_path / 'authority.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    ledger = PostgresKnowledgeLedger(sf)
    ledger.replace_catalog(_document(), _catalog(), now=NOW, actor="ingest-service")
    with sf() as session:
        claim_id = session.scalar(select(V2KnowledgeClaim.id))
    authority = (
        PostgresKnowledgeAuthority(sf, clock=clock)
        if clock is not None
        else PostgresKnowledgeAuthority(sf)
    )
    return ledger, authority, sf, claim_id


def _review(ledger, claim_id: str) -> None:
    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="reviewed",
        actor="domain-reviewer:alice",
        now=NOW,
        evidence=("ISO test reference",),
        applicability={"material": ["PTFE"]},
        uncertainty="conditional",
        transferability="family_level_orientation",
        review_expires_at=EXPIRY,
        change_reason="independent review",
    )


def _approve(ledger, claim_id: str) -> None:
    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="approved",
        actor="domain-approver:bob",
        now=NOW,
    )


def test_claim_lifecycle_rolls_postgres_epoch_and_tenant_binding(tmp_path) -> None:
    ledger, authority, _sf, claim_id = _fixture(tmp_path)
    draft = authority.capture(tenant_id="tenant-a")
    other_tenant = authority.capture(tenant_id="tenant-b")
    assert draft.sequence == 1
    assert draft.value != other_tenant.value

    _review(ledger, claim_id)
    reviewed = authority.capture(tenant_id="tenant-a")
    assert reviewed.sequence == draft.sequence + 1
    assert reviewed.value != draft.value

    _approve(ledger, claim_id)
    approved = authority.capture(tenant_id="tenant-a")
    assert approved.sequence == reviewed.sequence + 1
    assert approved.value != reviewed.value

    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="quarantined",
        actor="domain-reviewer:carol",
        now="2026-07-15T11:00:00Z",
        note="evidence conflict",
    )
    quarantined = authority.capture(tenant_id="tenant-a")
    assert quarantined.sequence == approved.sequence + 1
    assert quarantined.value != approved.value

    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="rejected",
        actor="domain-reviewer:carol",
        now="2026-07-15T12:00:00Z",
        note="claim revoked",
    )
    revoked = authority.capture(tenant_id="tenant-a")
    assert revoked.sequence == quarantined.sequence + 1
    assert revoked.value != quarantined.value

    ledger.replace_catalog(
        _document(b"authority-v2"),
        _catalog("PTFE cold flow depends on the application."),
        now="2026-07-15T13:00:00Z",
        actor="ingest-service",
    )
    updated = authority.capture(tenant_id="tenant-a")
    assert updated.sequence == revoked.sequence + 1
    assert updated.value != revoked.value


def test_expiry_changes_effective_epoch_without_scheduler_or_hour_window(
    tmp_path,
) -> None:
    clock = [datetime(2026, 7, 15, 12, tzinfo=timezone.utc)]
    ledger, authority, _sf, claim_id = _fixture(tmp_path, clock=lambda: clock[0])
    _review(ledger, claim_id)
    _approve(ledger, claim_id)
    before = authority.capture(tenant_id="tenant-a")

    clock[0] = datetime(2026, 7, 16, 10, 0, 1, tzinfo=timezone.utc)
    after = authority.capture(tenant_id="tenant-a")

    assert after.sequence == before.sequence
    assert after.value != before.value


def test_projection_sync_and_rebuild_metadata_cannot_mint_authority(tmp_path) -> None:
    _ledger, authority, sf, _claim_id = _fixture(tmp_path)
    before = authority.capture(tenant_id="tenant-a")

    with sf() as session:
        claim = session.scalar(select(V2KnowledgeClaim))
        outbox = session.scalar(select(V2KnowledgeOutbox))
        claim.qdrant_sync_state = "synced"
        claim.qdrant_synced_version = claim.version
        claim.qdrant_synced_at = "2026-07-15T10:01:00Z"
        outbox.status = "done"
        outbox.processed_at = "2026-07-15T10:01:00Z"
        session.commit()

    after = authority.capture(tenant_id="tenant-a")
    assert after == before


def test_request_guard_rejects_inflight_quarantine(tmp_path) -> None:
    ledger, authority, _sf, claim_id = _fixture(tmp_path)
    guard = RequestAuthorityGuard.bind(authority, tenant_id="tenant-a")

    ledger.review_claim(
        tenant_id=GLOBAL_KNOWLEDGE_TENANT,
        claim_id=claim_id,
        to_status="quarantined",
        actor="domain-reviewer:carol",
        now="2026-07-15T11:00:00Z",
        note="urgent quarantine",
    )

    with pytest.raises(KnowledgeAuthorityChanged):
        guard.recheck_before_serve()
