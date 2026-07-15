from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.knowledge.manufacturer_capability import (
    InProcessManufacturerCapabilityStore,
)
from sealai_v2.security.auth import FakeAuthValidator
from sealai_v2.tests.affiliation_fixtures import affiliation

IDENTITIES = {
    "manufacturer": VerifiedIdentity(
        "tenant-m",
        "session-m",
        "manufacturer-user",
        roles=("manufacturer",),
        hersteller_id="acme",
    ),
    "reviewer": VerifiedIdentity(
        "tenant-r",
        "session-r",
        "reviewer-user",
        roles=("capability_reviewer",),
    ),
    "self-reviewer": VerifiedIdentity(
        "tenant-m",
        "session-self",
        "manufacturer-reviewer-user",
        roles=("manufacturer", "capability_reviewer"),
        hersteller_id="acme",
    ),
    "connected-reviewer": VerifiedIdentity(
        "tenant-r",
        "session-connected",
        "connected-reviewer-user",
        roles=("capability_reviewer",),
    ),
    "operator-reviewer": VerifiedIdentity(
        "tenant-r",
        "session-operator",
        "operator-reviewer-user",
        roles=("capability_reviewer", "system_operator"),
    ),
    "admin": VerifiedIdentity(
        "tenant-a", "session-a", "owner-user", roles=("platform_owner",)
    ),
}


def _client():
    store = InProcessManufacturerCapabilityStore(
        affiliation_records=(
            affiliation("manufacturer-user", "acme"),
            affiliation("manufacturer-reviewer-user", "acme"),
            affiliation("reviewer-user", "reviewer-org"),
            affiliation("connected-reviewer-user", "acme"),
            affiliation("operator-reviewer-user", "operator-org"),
        )
    )
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDENTITIES)
    app.dependency_overrides[deps.get_capability_store] = lambda: store
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        capability_profiles_enabled=True
    )
    return TestClient(app), store


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_submission_and_independent_review_are_separate_roles() -> None:
    client, _ = _client()
    submitted = client.put(
        "/api/v2/partner/me/capability",
        headers=_auth("manufacturer"),
        json={
            "company_name": "ACME",
            "contacts": [
                {
                    "name": "A. Engineer",
                    "role": "Application",
                    "email": "a@acme.test",
                }
            ],
            "seal_types": ["RWDR"],
            "materials": ["FKM"],
            "application_limits": ["No oxygen service without separate review"],
            "change_reason": "initial",
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    denied = client.post(
        "/api/v2/admin/manufacturer-capabilities/acme/review",
        headers=_auth("manufacturer"),
        json={
            "to_status": "verified",
            "evidence": [{"citation": "audit report"}],
            "review_expires_at": "2027-07-11T20:00:00Z",
        },
    )
    assert denied.status_code == 403

    reviewed = client.post(
        "/api/v2/admin/manufacturer-capabilities/acme/review",
        headers=_auth("reviewer"),
        json={
            "to_status": "verified",
            "evidence": [{"citation": "audit report"}],
            "review_expires_at": "2027-07-11T20:00:00Z",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "verified"
    assert reviewed.json()["verified_by"] == "reviewer-user"
    assert reviewed.json()["contacts"][0]["role"] == "Application"
    assert reviewed.json()["application_limits"]

    listed = client.get(
        "/api/v2/admin/manufacturer-capabilities", headers=_auth("admin")
    )
    assert listed.status_code == 200
    assert listed.json()["profiles"][0]["manufacturer_id"] == "acme"


def test_manufacturer_with_reviewer_role_cannot_self_verify() -> None:
    client, _ = _client()
    client.put(
        "/api/v2/partner/me/capability",
        headers=_auth("manufacturer"),
        json={"company_name": "ACME"},
    )

    response = client.post(
        "/api/v2/admin/manufacturer-capabilities/acme/review",
        headers=_auth("self-reviewer"),
        json={
            "to_status": "verified",
            "evidence": [{"citation": "self-issued statement"}],
            "review_expires_at": "2027-07-11T20:00:00Z",
        },
    )

    assert response.status_code == 403


def test_client_coi_attestation_is_rejected_and_server_relationship_blocks() -> None:
    client, _ = _client()
    client.put(
        "/api/v2/partner/me/capability",
        headers=_auth("manufacturer"),
        json={"company_name": "ACME"},
    )

    client_assertion = client.post(
        "/api/v2/admin/manufacturer-capabilities/acme/review",
        headers=_auth("reviewer"),
        json={
            "to_status": "verified",
            "evidence": [{"citation": "audit report"}],
            "review_expires_at": "2027-07-11T20:00:00Z",
            "conflict_of_interest": "none_declared",
        },
    )
    assert client_assertion.status_code == 422

    connected = client.post(
        "/api/v2/admin/manufacturer-capabilities/acme/review",
        headers=_auth("connected-reviewer"),
        json={
            "to_status": "verified",
            "evidence": [{"citation": "audit report"}],
            "review_expires_at": "2027-07-11T20:00:00Z",
        },
    )
    assert connected.status_code == 400
    assert connected.json() == {"detail": {"code": "capability_review_invalid"}}

    incompatible = client.post(
        "/api/v2/admin/manufacturer-capabilities/acme/review",
        headers=_auth("operator-reviewer"),
        json={"to_status": "quarantined"},
    )
    assert incompatible.status_code == 403

    independent = client.post(
        "/api/v2/admin/manufacturer-capabilities/acme/review",
        headers=_auth("reviewer"),
        json={
            "to_status": "verified",
            "evidence": [{"citation": "independent audit"}],
            "review_expires_at": "2027-07-11T20:00:00Z",
        },
    )
    assert independent.status_code == 200
    assert independent.json()["status"] == "verified"


def test_capability_surface_is_default_off() -> None:
    client, _ = _client()
    app.dependency_overrides[deps.get_settings] = lambda: Settings()

    response = client.get(
        "/api/v2/partner/me/capability", headers=_auth("manufacturer")
    )

    assert response.status_code == 503
    assert response.json()["detail"]["mode"] == "capability_profiles"
