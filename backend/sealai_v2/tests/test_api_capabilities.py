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
    "admin": VerifiedIdentity("tenant-a", "session-a", "admin-user", roles=("admin",)),
}


def _client():
    store = InProcessManufacturerCapabilityStore()
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
            "conflict_of_interest": "none_declared",
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
            "conflict_of_interest": "none_declared",
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
            "conflict_of_interest": "none_declared",
        },
    )

    assert response.status_code == 403


def test_capability_surface_is_default_off() -> None:
    client, _ = _client()
    app.dependency_overrides[deps.get_settings] = lambda: Settings()

    response = client.get(
        "/api/v2/partner/me/capability", headers=_auth("manufacturer")
    )

    assert response.status_code == 503
    assert response.json()["detail"]["mode"] == "capability_profiles"
