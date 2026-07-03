"""/api/v2/memory — sealingAI Memory Architecture V1.0, Patch 3 (API Basics). Every op is
tenant-scoped from the verified token only (P0, same discipline as test_api_conversations.py's
cross-tenant isolation coverage)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.api.routes import memory_v2
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.memory_store import InProcessMemoryStore
from sealai_v2.security.auth import FakeAuthValidator

IDS = {
    "tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A"),
    "tok-B": VerifiedIdentity("tenant-B", "sess-B", "user-B"),
}


def _client(store: InProcessMemoryStore | None = None):
    store = store if store is not None else InProcessMemoryStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDS)
    app.dependency_overrides[memory_v2.get_memory_store] = lambda: store
    return TestClient(app), store


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_VALID_CANDIDATE = {
    "scope": "session",
    "scope_id": "sess-A",
    "type": "preference",
    "content": "prefers metric units",
    "semantic_key": "pref:units:metric",
    "sources": [{"kind": "user_stated", "session_id": "sess-A"}],
}


def test_create_candidate_requires_auth():
    client, _store = _client()
    r = client.post("/api/v2/memory/candidates", json=_VALID_CANDIDATE)
    assert r.status_code == 401


def test_create_candidate_rejects_missing_sources():
    client, _store = _client()
    body = {**_VALID_CANDIDATE, "sources": []}
    r = client.post("/api/v2/memory/candidates", json=body, headers=_auth("tok-A"))
    assert r.status_code == 422
    assert "Source/Provenance" in r.json()["detail"]


def test_create_candidate_succeeds_and_returns_the_item():
    client, _store = _client()
    r = client.post(
        "/api/v2/memory/candidates", json=_VALID_CANDIDATE, headers=_auth("tok-A")
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "candidate"
    assert body["tenant_id"] == "tenant-A"
    assert body["content"] == "prefers metric units"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["kind"] == "user_stated"


def test_create_then_list_roundtrip_within_same_tenant():
    client, _store = _client()
    client.post(
        "/api/v2/memory/candidates", json=_VALID_CANDIDATE, headers=_auth("tok-A")
    )
    r = client.get("/api/v2/memory/items", headers=_auth("tok-A"))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["content"] == "prefers metric units"


def test_list_items_never_leaks_across_tenants():
    client, _store = _client()
    client.post(
        "/api/v2/memory/candidates", json=_VALID_CANDIDATE, headers=_auth("tok-A")
    )
    r = client.get("/api/v2/memory/items", headers=_auth("tok-B"))
    assert r.status_code == 200
    assert r.json()["items"] == []  # tenant B sees NONE of tenant A's items


def test_summary_never_leaks_across_tenants():
    client, _store = _client()
    client.post(
        "/api/v2/memory/candidates", json=_VALID_CANDIDATE, headers=_auth("tok-A")
    )
    r = client.get("/api/v2/memory/summary", headers=_auth("tok-B"))
    assert r.status_code == 200
    assert r.json() == {"total": 0, "by_status": {}, "by_scope": {}}


def test_summary_counts_by_status_and_scope():
    client, _store = _client()
    client.post(
        "/api/v2/memory/candidates", json=_VALID_CANDIDATE, headers=_auth("tok-A")
    )
    second = {
        **_VALID_CANDIDATE,
        "scope": "case",
        "scope_id": "case-1",
        "type": "case_parameter",
        "semantic_key": "case:case-1:medium",
    }
    client.post("/api/v2/memory/candidates", json=second, headers=_auth("tok-A"))
    r = client.get("/api/v2/memory/summary", headers=_auth("tok-A"))
    body = r.json()
    assert body["total"] == 2
    assert body["by_status"] == {"candidate": 2}
    assert body["by_scope"] == {"session": 1, "case": 1}


def test_list_items_filters_by_status():
    client, _store = _client()
    client.post(
        "/api/v2/memory/candidates", json=_VALID_CANDIDATE, headers=_auth("tok-A")
    )
    r = client.get(
        "/api/v2/memory/items", params={"status": "confirmed"}, headers=_auth("tok-A")
    )
    assert r.json()["items"] == []  # nothing is confirmed yet — only a candidate exists


def test_list_items_filters_by_case_id():
    client, _store = _client()
    case_item = {
        **_VALID_CANDIDATE,
        "scope": "case",
        "scope_id": "case-1",
        "type": "case_parameter",
        "semantic_key": "case:case-1:medium",
    }
    client.post("/api/v2/memory/candidates", json=case_item, headers=_auth("tok-A"))
    client.post(
        "/api/v2/memory/candidates", json=_VALID_CANDIDATE, headers=_auth("tok-A")
    )  # session-scoped, not case-1
    r = client.get(
        "/api/v2/memory/items", params={"case_id": "case-1"}, headers=_auth("tok-A")
    )
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["scope"] == "case" and items[0]["scope_id"] == "case-1"


def test_create_candidate_rejects_invalid_type_enum():
    client, _store = _client()
    body = {**_VALID_CANDIDATE, "type": "not_a_real_type"}
    r = client.post("/api/v2/memory/candidates", json=body, headers=_auth("tok-A"))
    assert r.status_code == 422
