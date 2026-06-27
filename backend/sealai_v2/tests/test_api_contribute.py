"""Wissens-Beitrag /api/v2/contribute + /admin/contributions. Proves: a user contributes (anonymous DROPS
identity; named keeps provenance), it lands as an untrusted DRAFT in the owner review queue (admin-only),
the owner can set its status; the contribution NEVER touches the pipeline."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.contributions import InProcessContributionStore
from sealai_v2.security.auth import FakeAuthValidator

IDS = {
    "tok-user": VerifiedIdentity("tenant-A", "sess-A", "user-A"),
    "tok-admin": VerifiedIdentity("tenant-O", "sess-O", "owner", roles=("admin",)),
}


def _client(store=None):
    store = store if store is not None else InProcessContributionStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDS)
    app.dependency_overrides[deps.get_contribution_store] = lambda: store
    return TestClient(app), store


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_anonymous_contribution_drops_identity():
    client, store = _client()
    r = client.post(
        "/api/v2/contribute",
        json={
            "anonym": True,
            "situation": "FKM RWDR 150C",
            "outcome": "hat funktioniert",
            "case_state": [{"feld": "medium", "wert": "Öl"}],
        },
        headers=_auth("tok-user"),
    )
    assert (
        r.status_code == 200
        and r.json()["status"] == "captured"
        and r.json()["anonym"] is True
    )
    c = store.list_all()[0]
    assert (
        c.anonym is True and c.tenant_ref == "anon" and c.subject_ref == ""
    )  # NO identity
    assert c.outcome == "hat funktioniert" and c.status == "neu"
    assert c.case_state_json == [{"feld": "medium", "wert": "Öl"}]


def test_named_contribution_keeps_provenance():
    client, store = _client()
    client.post(
        "/api/v2/contribute",
        json={"anonym": False, "outcome": "ok"},
        headers=_auth("tok-user"),
    )
    c = store.list_all()[0]
    assert (
        c.anonym is False and c.tenant_ref == "tenant-A" and c.subject_ref == "user-A"
    )


def test_contribute_requires_auth():
    client, _ = _client()
    assert client.post("/api/v2/contribute", json={"outcome": "x"}).status_code == 401


def test_review_queue_is_admin_only():
    client, _ = _client()
    assert (
        client.get("/api/v2/admin/contributions", headers=_auth("tok-user")).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v2/admin/contributions", headers=_auth("tok-admin")
        ).status_code
        == 200
    )


def test_owner_lists_and_sets_status():
    store = InProcessContributionStore()
    client, _ = _client(store=store)
    client.post(
        "/api/v2/contribute",
        json={"anonym": True, "outcome": "FKM hielt"},
        headers=_auth("tok-user"),
    )
    listed = client.get(
        "/api/v2/admin/contributions", headers=_auth("tok-admin")
    ).json()["contributions"]
    assert len(listed) == 1 and listed[0]["outcome"] == "FKM hielt"
    cid = listed[0]["id"]
    r = client.put(
        f"/api/v2/admin/contributions/{cid}/status",
        json={"status": "promoted", "review_note": "→ field_validated Fachkarte"},
        headers=_auth("tok-admin"),
    )
    assert r.status_code == 200
    assert (
        client.get("/api/v2/admin/contributions", headers=_auth("tok-admin")).json()[
            "contributions"
        ][0]["status"]
        == "promoted"
    )


def test_invalid_status_rejected():
    store = InProcessContributionStore()
    client, _ = _client(store=store)
    client.post(
        "/api/v2/contribute",
        json={"anonym": True, "outcome": "x"},
        headers=_auth("tok-user"),
    )
    cid = store.list_all()[0].id
    assert (
        client.put(
            f"/api/v2/admin/contributions/{cid}/status",
            json={"status": "bogus"},
            headers=_auth("tok-admin"),
        ).status_code
        == 422
    )
