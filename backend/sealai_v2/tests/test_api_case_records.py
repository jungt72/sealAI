from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.decision_records import InProcessCaseDecisionStore
from sealai_v2.security.auth import FakeAuthValidator

IDENTITIES = {
    "owner-a": VerifiedIdentity("tenant-a", "session-a", "owner-a"),
    "owner-b": VerifiedIdentity("tenant-b", "session-b", "owner-b"),
    "owner-c": VerifiedIdentity("tenant-a", "session-c", "owner-c"),
    "reviewer-a": VerifiedIdentity(
        "tenant-a",
        "session-r",
        "reviewer-a",
        roles=("decision_reviewer",),
    ),
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_case_api_preserves_tenant_boundary_and_release_boundary() -> None:
    store = InProcessCaseDecisionStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDENTITIES)
    app.dependency_overrides[deps.get_case_decision_store] = lambda: store
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        case_decision_records_enabled=True
    )
    client = TestClient(app)

    created = client.post(
        "/api/v2/cases",
        headers=_auth("owner-a"),
        json={"title": "RWDR Case", "risk_class": "D"},
    )
    assert created.status_code == 200
    case_id = created.json()["case"]["case_id"]
    snapshot = client.post(
        f"/api/v2/cases/{case_id}/snapshots",
        headers=_auth("owner-a"),
        json={
            "state": {"seal_type": "RWDR"},
            "evidence_refs": ["claim:123"],
            "open_points": ["shaft hardness"],
        },
    )
    snapshot_id = snapshot.json()["snapshot"]["id"]
    decision = client.post(
        f"/api/v2/cases/{case_id}/decisions",
        headers=_auth("owner-a"),
        json={
            "snapshot_id": snapshot_id,
            "decision_type": "technical_orientation",
            "conclusion": "Manufacturer validation required",
            "rationale": "Open component constraint",
            "evidence_refs": ["claim:123"],
            "uncertainty": "conditional",
            "responsibilities": {"manufacturer": "component validation"},
        },
    )
    assert decision.status_code == 200
    assert (
        decision.json()["release_authority"]
        == "external_manufacturer_or_responsible_engineer"
    )
    decision_id = decision.json()["decision"]["id"]
    approval = client.post(
        f"/api/v2/cases/decisions/{decision_id}/approvals",
        headers=_auth("reviewer-a"),
        json={"status": "approved", "note": "trace checked"},
    )
    assert approval.status_code == 200
    assert approval.json()["approval"]["approval_kind"] == "technical_review"

    denied = client.get(f"/api/v2/cases/{case_id}", headers=_auth("owner-b"))
    assert denied.status_code == 404
    same_tenant_denied = client.get(
        f"/api/v2/cases/{case_id}", headers=_auth("owner-c")
    )
    assert same_tenant_denied.status_code == 404
    same_tenant_mutation_denied = client.post(
        f"/api/v2/cases/{case_id}/snapshots",
        headers=_auth("owner-c"),
        json={"state": {"seal_type": "O-Ring"}},
    )
    assert same_tenant_mutation_denied.status_code == 404
    bundle = client.get(f"/api/v2/cases/{case_id}", headers=_auth("owner-a"))
    assert bundle.status_code == 200
    assert "keine Bauteil" in bundle.json()["release_boundary"]


def test_case_record_surface_is_default_off() -> None:
    store = InProcessCaseDecisionStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDENTITIES)
    app.dependency_overrides[deps.get_case_decision_store] = lambda: store
    app.dependency_overrides[deps.get_settings] = lambda: Settings()

    response = TestClient(app).post(
        "/api/v2/cases",
        headers=_auth("owner-a"),
        json={"title": "RWDR Case"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["mode"] == "case_decision_records"
