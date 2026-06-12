"""M6c — /api/v2/conversations: the M5 view / edit / forget surface, all token-scoped. The
cross-tenant isolation test covers MUTATIONS (req 3): tenant A's token cannot edit/forget tenant B's
facts."""

from __future__ import annotations

from sealai_v2.tests._apiutil import auth, make_client


def _seed(pipeline, tenant, session, feld, wert):
    from sealai_v2.core.contracts import RememberedFact

    pipeline.memory.record_turn(
        tenant_id=tenant,
        session_id=session,
        question="q",
        answer="a",
        facts=(RememberedFact(feld, wert),),
    )


def test_view_edit_forget_roundtrip():
    client, pipeline = make_client()
    _seed(pipeline, "tenant-A", "sess-A", "medium", "Hydrauliköl")
    # view
    r = client.get("/api/v2/conversations/current/memory", headers=auth("tok-A"))
    assert {
        "feld": "medium",
        "wert": "Hydrauliköl",
        "provenance": "distilled-from-conversation",
    } in r.json()["case_state"]
    # edit
    client.put(
        "/api/v2/conversations/current/facts/medium",
        json={"wert": "Wasser"},
        headers=auth("tok-A"),
    )
    cs = client.get(
        "/api/v2/conversations/current/memory", headers=auth("tok-A")
    ).json()["case_state"]
    assert any(f["feld"] == "medium" and f["wert"] == "Wasser" for f in cs)
    # forget one
    client.delete("/api/v2/conversations/current/facts/medium", headers=auth("tok-A"))
    cs = client.get(
        "/api/v2/conversations/current/memory", headers=auth("tok-A")
    ).json()["case_state"]
    assert not any(f["feld"] == "medium" for f in cs)


def test_forget_all_clears_only_callers_tenant():
    client, pipeline = make_client()
    _seed(pipeline, "tenant-A", "sess-A", "medium", "Öl")
    _seed(pipeline, "tenant-B", "sess-B", "medium", "Wasser")
    client.delete("/api/v2/conversations/current", headers=auth("tok-A"))  # A clears
    assert pipeline.memory.case_state(tenant_id="tenant-A", session_id="sess-A") == ()
    assert pipeline.memory.case_state(
        tenant_id="tenant-B", session_id="sess-B"
    )  # B untouched


def test_form_origin_sets_user_form_provenance():
    # the parameter form tags inputs origin=user-form (distinct from chat-distilled / inline edit) so
    # a form-entered value's calc citation can name the source honestly.
    client, pipeline = make_client()
    client.put(
        "/api/v2/conversations/current/facts/wellendurchmesser",
        json={"wert": "50 mm", "origin": "user-form"},
        headers=auth("tok-A"),
    )
    (f,) = pipeline.memory.case_state(tenant_id="tenant-A", session_id="sess-A")
    assert f.feld == "wellendurchmesser" and f.wert == "50 mm"
    assert f.provenance == "user-form"


def test_edit_without_origin_defaults_to_user_edited():
    # the inline MemoryPanel edit (no origin) keeps the existing user-edited provenance.
    client, pipeline = make_client()
    client.put(
        "/api/v2/conversations/current/facts/medium",
        json={"wert": "Wasser"},
        headers=auth("tok-A"),
    )
    (f,) = pipeline.memory.case_state(tenant_id="tenant-A", session_id="sess-A")
    assert f.provenance == "user-edited"


def test_unknown_origin_fails_closed_to_user_edited():
    # allowlist: an unrecognized origin is NOT honored (no provenance spoofing) — falls back honestly.
    client, pipeline = make_client()
    client.put(
        "/api/v2/conversations/current/facts/medium",
        json={"wert": "Wasser", "origin": "reviewed"},
        headers=auth("tok-A"),
    )
    (f,) = pipeline.memory.case_state(tenant_id="tenant-A", session_id="sess-A")
    assert f.provenance == "user-edited"


def test_cross_tenant_MUTATION_isolation_via_token():
    # req 3: tenant A's token cannot edit OR forget tenant B's facts — the route scopes by the token.
    client, pipeline = make_client()
    _seed(pipeline, "tenant-B", "sess-B", "medium", "Wasser")
    # A edits "medium" — affects A's (empty) session, NEVER B's
    client.put(
        "/api/v2/conversations/current/facts/medium",
        json={"wert": "HACKED"},
        headers=auth("tok-A"),
    )
    b = pipeline.memory.case_state(tenant_id="tenant-B", session_id="sess-B")
    assert any(
        f.feld == "medium" and f.wert == "Wasser" for f in b
    )  # B intact, not "HACKED"
    # A forgets "medium" — B's fact survives
    client.delete("/api/v2/conversations/current/facts/medium", headers=auth("tok-A"))
    assert pipeline.memory.case_state(
        tenant_id="tenant-B", session_id="sess-B"
    )  # still there
