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


# --- "Fälle"-Sidebar Patch B: optional case_id override ---


def test_chat_without_case_id_uses_the_tokens_session():
    # byte-identical to before this patch: omitting case_id records under identity.session_id.
    client, pipeline = make_client()
    client.post("/api/v2/chat", json={"message": "ohne case_id"}, headers=auth("tok-A"))
    assert pipeline.memory.history(tenant_id="tenant-A", session_id="sess-A")


def test_chat_with_case_id_targets_that_case_not_the_tokens_session():
    client, pipeline = make_client()
    client.post(
        "/api/v2/chat",
        json={"message": "in Fall 2", "case_id": "case-2"},
        headers=auth("tok-A"),
    )
    assert pipeline.memory.history(tenant_id="tenant-A", session_id="case-2")
    assert pipeline.memory.history(tenant_id="tenant-A", session_id="sess-A") == ()


def test_two_case_ids_from_the_same_identity_stay_fully_isolated():
    client, pipeline = make_client()
    client.post(
        "/api/v2/chat",
        json={"message": "Fall 1: EPDM", "case_id": "case-1"},
        headers=auth("tok-A"),
    )
    client.post(
        "/api/v2/chat",
        json={"message": "Fall 2: FKM", "case_id": "case-2"},
        headers=auth("tok-A"),
    )
    h1 = pipeline.memory.history(tenant_id="tenant-A", session_id="case-1")
    h2 = pipeline.memory.history(tenant_id="tenant-A", session_id="case-2")
    assert any("EPDM" in t.text for t in h1) and not any("FKM" in t.text for t in h1)
    assert any("FKM" in t.text for t in h2) and not any("EPDM" in t.text for t in h2)


def test_same_tenant_user_cannot_continue_another_users_case_id():
    client, pipeline = make_client()
    first = client.post(
        "/api/v2/chat",
        json={"message": "privater Fall", "case_id": "shared-id"},
        headers=auth("tok-A"),
    )
    assert first.status_code == 200

    denied = client.post(
        "/api/v2/chat",
        json={"message": "Übernahmeversuch", "case_id": "shared-id"},
        headers=auth("tok-A2"),
    )
    assert denied.status_code == 404
    history = pipeline.memory.history(tenant_id="tenant-A", session_id="shared-id")
    assert not any("Übernahmeversuch" in turn.text for turn in history)


def test_case_id_never_crosses_the_tenant_boundary():
    # tok-A naming tenant-B's real session id as case_id must still write under tenant-A — the
    # token, never the client-supplied case_id, decides the tenant (P0).
    client, pipeline = make_client()
    client.post(
        "/api/v2/chat",
        json={"message": "versuchter Cross-Tenant-Zugriff", "case_id": "sess-B"},
        headers=auth("tok-A"),
    )
    assert pipeline.memory.history(tenant_id="tenant-A", session_id="sess-B")
    assert pipeline.memory.history(tenant_id="tenant-B", session_id="sess-B") == ()


def test_case_id_over_255_chars_is_a_clean_422_not_a_db_500():
    # 2026-07-04 audit finding: case_id had no length constraint, so an over-long value hit the
    # DB's own String(255) column and surfaced as a generic 500 instead of a validation error.
    client, _ = make_client()
    r = client.post(
        "/api/v2/chat",
        json={"message": "x", "case_id": "a" * 256},
        headers=auth("tok-A"),
    )
    assert r.status_code == 422


def test_case_id_at_exactly_255_chars_is_accepted():
    client, _ = make_client()
    r = client.post(
        "/api/v2/chat",
        json={"message": "x", "case_id": "a" * 255},
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
