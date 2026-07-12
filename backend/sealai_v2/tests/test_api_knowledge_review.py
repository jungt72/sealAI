from __future__ import annotations

from fastapi.testclient import TestClient

import sealai_v2.db.models  # noqa: F401
from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    KnowledgeDocumentInput,
    PostgresKnowledgeLedger,
)
from sealai_v2.security.auth import FakeAuthValidator

NOW = "2026-07-11T10:00:00Z"


def _client(tmp_path, *, review_enabled: bool = True):
    engine = make_engine(f"sqlite:///{tmp_path / 'knowledge-review.db'}")
    Base.metadata.create_all(engine)
    ledger = PostgresKnowledgeLedger(make_sessionmaker(engine))
    catalog = FachkartenCatalog(
        cards=(
            _card(
                {
                    "id": "FK-REVIEW",
                    "scope": {"material": ["PTFE"]},
                    "claims": [
                        {
                            "text": "PTFE requires application-specific assessment.",
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
    ledger.replace_catalog(
        KnowledgeDocumentInput(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            source_type="review_fixture",
            source_id="1",
            source_uri="fixture:1",
            object_key="fixture:1",
            title="Review fixture",
            content=b"review fixture",
            authority="unreviewed",
        ),
        catalog,
        now=NOW,
        actor="ingest-service",
    )
    identities = {
        "reviewer": VerifiedIdentity(
            "review-tenant",
            "review-session",
            "human-reviewer",
            roles=("knowledge_reviewer",),
        ),
        "user": VerifiedIdentity("tenant-a", "session-a", "user-a"),
    }
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(identities)
    app.dependency_overrides[deps.get_knowledge_ledger] = lambda: ledger
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        knowledge_review_enabled=review_enabled
    )
    return TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_review_queue_requires_role_and_independent_attestation(tmp_path) -> None:
    client = _client(tmp_path)
    denied = client.get(
        "/api/v2/admin/knowledge/claims?status=draft", headers=_auth("user")
    )
    assert denied.status_code == 403

    listed = client.get(
        "/api/v2/admin/knowledge/claims?status=draft", headers=_auth("reviewer")
    )
    assert listed.status_code == 200
    claim_id = listed.json()["claims"][0]["claim_id"]

    missing_attestation = client.post(
        f"/api/v2/admin/knowledge/claims/{claim_id}/review",
        headers=_auth("reviewer"),
        json={"to_status": "approved"},
    )
    assert missing_attestation.status_code == 400

    approved = client.post(
        f"/api/v2/admin/knowledge/claims/{claim_id}/review",
        headers=_auth("reviewer"),
        json={
            "to_status": "approved",
            "independent_review_attested": True,
            "evidence": [{"citation": "ISO test reference", "document_id": "doc-1"}],
            "applicability": {"material": ["PTFE"]},
            "uncertainty": "conditional",
            "transferability": "family_level_orientation",
            "review_expires_at": "2099-07-11T10:00:00Z",
            "change_reason": "Independent domain review",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["claim"]["review_status"] == "approved"
    assert approved.json()["claim"]["reviewed_by"] == "human-reviewer"
    assert approved.json()["claim"]["review_origin"] == "human_api"
    assert approved.json()["knowledge_mode_activated"] is False


def test_review_queue_is_default_off(tmp_path) -> None:
    client = _client(tmp_path, review_enabled=False)

    response = client.get(
        "/api/v2/admin/knowledge/claims?status=draft", headers=_auth("reviewer")
    )

    assert response.status_code == 503
    assert response.json()["detail"]["mode"] == "knowledge_review"
