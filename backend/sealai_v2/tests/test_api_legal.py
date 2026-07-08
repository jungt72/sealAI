"""/api/v2/legal/* — doctrine (public) + acceptance submit/status (Legal-by-Design Phase A+B)."""

from __future__ import annotations

from sealai_v2.core.legal_doctrine import doctrine_payload
from sealai_v2.db.legal_acceptance import InProcessLegalAcceptanceStore
from sealai_v2.tests._apiutil import auth, make_client


def _client(store=None):
    from sealai_v2.api import deps
    from sealai_v2.api.main import app

    client, _pipeline = make_client()
    store = store if store is not None else InProcessLegalAcceptanceStore()
    app.dependency_overrides[deps.get_legal_acceptance_store] = lambda: store
    return client, store


def test_doctrine_is_public_no_token_required():
    client, _ = _client()
    r = client.get("/api/v2/legal/doctrine")
    assert r.status_code == 200
    body = r.json()
    assert body == doctrine_payload()


def _valid_body(**over):
    d = doctrine_payload()
    base = {
        "company_name": "ACME Dichtungen GmbH",
        "business_email": "einkauf@acme-dichtungen.example",
        "role": "Einkauf",
        "vat_id": "DE123456789",
        "legal_basis_accepted": True,
        "dpa_accepted": True,
        "business_user_confirmed": True,
        "terms_version": d["terms_version"],
        "privacy_version": d["privacy_version"],
        "dpa_version": d["dpa_version"],
    }
    base.update(over)
    return base


def test_acceptance_requires_a_token():
    client, _ = _client()
    r = client.post("/api/v2/legal/acceptance", json=_valid_body())
    assert r.status_code == 401


def test_valid_acceptance_is_stored_under_the_tokens_tenant():
    client, store = _client()
    r = client.post("/api/v2/legal/acceptance", json=_valid_body(), headers=auth("tok-A"))
    assert r.status_code == 200
    got = store.get("tenant-A")
    assert got is not None
    assert got.company_name == "ACME Dichtungen GmbH"


def test_freemail_business_email_is_rejected():
    client, store = _client()
    r = client.post(
        "/api/v2/legal/acceptance",
        json=_valid_body(business_email="privat@gmail.com"),
        headers=auth("tok-A"),
    )
    assert r.status_code == 422
    assert store.get("tenant-A") is None


def test_missing_legal_basis_checkbox_is_rejected():
    client, store = _client()
    r = client.post(
        "/api/v2/legal/acceptance",
        json=_valid_body(legal_basis_accepted=False),
        headers=auth("tok-A"),
    )
    assert r.status_code == 422
    assert store.get("tenant-A") is None


def test_missing_dpa_checkbox_is_rejected():
    client, store = _client()
    r = client.post(
        "/api/v2/legal/acceptance",
        json=_valid_body(dpa_accepted=False),
        headers=auth("tok-A"),
    )
    assert r.status_code == 422
    assert store.get("tenant-A") is None


def test_missing_business_user_confirmation_is_rejected():
    client, store = _client()
    r = client.post(
        "/api/v2/legal/acceptance",
        json=_valid_body(business_user_confirmed=False),
        headers=auth("tok-A"),
    )
    assert r.status_code == 422
    assert store.get("tenant-A") is None


def test_stale_terms_version_is_a_conflict():
    client, store = _client()
    r = client.post(
        "/api/v2/legal/acceptance",
        json=_valid_body(terms_version="2020-01-01-v0"),
        headers=auth("tok-A"),
    )
    assert r.status_code == 409
    assert store.get("tenant-A") is None


def test_malformed_email_is_rejected():
    client, _ = _client()
    r = client.post(
        "/api/v2/legal/acceptance",
        json=_valid_body(business_email="not-an-email"),
        headers=auth("tok-A"),
    )
    assert r.status_code == 422


def test_acceptance_status_false_before_submission():
    client, _ = _client()
    r = client.get("/api/v2/legal/acceptance-status", headers=auth("tok-A"))
    assert r.status_code == 200
    assert r.json() == {"accepted": False}


def test_acceptance_status_true_after_submission():
    client, _ = _client()
    client.post("/api/v2/legal/acceptance", json=_valid_body(), headers=auth("tok-A"))
    r = client.get("/api/v2/legal/acceptance-status", headers=auth("tok-A"))
    assert r.json() == {"accepted": True}


def test_acceptance_is_tenant_scoped_not_shared():
    client, _ = _client()
    client.post("/api/v2/legal/acceptance", json=_valid_body(), headers=auth("tok-A"))
    r = client.get("/api/v2/legal/acceptance-status", headers=auth("tok-B"))
    assert r.json() == {"accepted": False}
