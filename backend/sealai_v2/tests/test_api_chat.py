"""M6c — /api/v2/chat route + the P0 guarantees: missing/invalid token → 401; identity ONLY from the
token (no-header-trust); cross-tenant isolation driven by the verified token (reads)."""

from __future__ import annotations

from sealai_v2.tests._apiutil import auth, make_client


def test_chat_projects_the_pipeline():
    client, _ = make_client(pipeline=None)
    r = client.post(
        "/api/v2/chat", json={"message": "Was ist FKM?"}, headers=auth("tok-A")
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Antwort." and "citations" in body and "grounded" in body


def test_missing_token_is_401():
    client, _ = make_client()
    assert client.post("/api/v2/chat", json={"message": "x"}).status_code == 401


def test_invalid_token_is_401():
    client, _ = make_client()
    r = client.post("/api/v2/chat", json={"message": "x"}, headers=auth("tok-UNKNOWN"))
    assert r.status_code == 401


def test_no_header_trust_uses_token_tenant_not_spoofed_header():
    client, pipeline = make_client()
    # chat as tenant-A, but spoof a tenant-B header — the route must IGNORE it (uses the token).
    r = client.post(
        "/api/v2/chat",
        json={"message": "EPDM in Hydrauliköl?"},
        headers={**auth("tok-A"), "X-Tenant-Id": "tenant-B", "X-Session-Id": "sess-B"},
    )
    assert r.status_code == 200
    mem = pipeline.memory
    # the turn landed under the TOKEN's identity (tenant-A/sess-A), NOT the spoofed header
    assert mem.history(tenant_id="tenant-A", session_id="sess-A")  # present
    assert mem.history(tenant_id="tenant-B", session_id="sess-B") == ()  # spoof ignored


def test_cross_tenant_read_isolation_via_token():
    client, pipeline = make_client()
    client.post("/api/v2/chat", json={"message": "Fall A"}, headers=auth("tok-A"))
    # tenant-B's token sees its OWN (empty) memory, never tenant-A's turn
    r = client.get("/api/v2/conversations/current/memory", headers=auth("tok-B"))
    assert r.status_code == 200 and r.json()["history"] == []
    rA = client.get("/api/v2/conversations/current/memory", headers=auth("tok-A"))
    assert any("Fall A" in t["text"] for t in rA.json()["history"])
