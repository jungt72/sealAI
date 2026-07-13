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
        owner_subject="user-A" if tenant == "tenant-A" else "user-B",
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


def test_list_conversations_returns_cases_with_metadata():
    client, pipeline = make_client()
    _seed(pipeline, "tenant-A", "sess-A", "medium", "Öl")
    r = client.get("/api/v2/conversations", headers=auth("tok-A"))
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["case_id"] == "sess-A"
    # _seed's record_turn() doesn't pass now (mirrors the pipeline's own remember-stage default
    # being the only real caller) — title/timestamps stay None, exactly like an existing session
    # that predates this feature.
    assert cases[0]["title"] is None


def test_list_conversations_never_leaks_across_tenants():
    client, pipeline = make_client()
    _seed(pipeline, "tenant-A", "sess-A", "medium", "Öl")
    _seed(pipeline, "tenant-B", "sess-B", "medium", "Wasser")
    r = client.get("/api/v2/conversations", headers=auth("tok-A"))
    case_ids = {c["case_id"] for c in r.json()["cases"]}
    assert case_ids == {"sess-A"}


def test_same_tenant_user_cannot_list_read_or_mutate_another_users_conversation():
    client, pipeline = make_client()
    _seed(pipeline, "tenant-A", "private-A", "medium", "Öl")

    listed = client.get("/api/v2/conversations", headers=auth("tok-A2"))
    assert listed.status_code == 200
    assert listed.json()["cases"] == []

    read = client.get(
        "/api/v2/conversations/current/memory",
        params={"case_id": "private-A"},
        headers=auth("tok-A2"),
    )
    assert read.status_code == 404

    edit = client.put(
        "/api/v2/conversations/current/facts/medium",
        params={"case_id": "private-A"},
        json={"wert": "HACKED"},
        headers=auth("tok-A2"),
    )
    assert edit.status_code == 404
    assert (
        pipeline.memory.case_state(tenant_id="tenant-A", session_id="private-A")[0].wert
        == "Öl"
    )


def test_case_id_query_param_overrides_the_tokens_session_for_view_memory():
    # "Fälle"-Sidebar (Patch A): a tenant can view a DIFFERENT one of its own cases by passing
    # ?case_id=..., not just the token-derived "current" one.
    client, pipeline = make_client()
    _seed(pipeline, "tenant-A", "sess-A", "medium", "Öl")
    _seed(pipeline, "tenant-A", "case-2", "medium", "Wasser")
    default = client.get(
        "/api/v2/conversations/current/memory", headers=auth("tok-A")
    ).json()
    assert any(f["wert"] == "Öl" for f in default["case_state"])
    other = client.get(
        "/api/v2/conversations/current/memory",
        params={"case_id": "case-2"},
        headers=auth("tok-A"),
    ).json()
    assert any(f["wert"] == "Wasser" for f in other["case_state"])
    assert not any(f["wert"] == "Öl" for f in other["case_state"])


def test_case_id_naming_a_foreign_tenants_session_returns_empty_not_leaked():
    # tenant-A's token + case_id="sess-B" (a REAL session, but belonging to tenant-B) must resolve
    # to nothing — the (tenant_id, case_id) tuple matches no row for tenant-A, same as any unused
    # session_id today; never tenant-B's data.
    client, pipeline = make_client()
    _seed(pipeline, "tenant-B", "sess-B", "medium", "Wasser")
    r = client.get(
        "/api/v2/conversations/current/memory",
        params={"case_id": "sess-B"},
        headers=auth("tok-A"),
    ).json()
    assert r["case_state"] == []
    assert r["history"] == []


def test_case_id_query_param_overrides_for_edit_and_forget_too():
    client, pipeline = make_client()
    _seed(pipeline, "tenant-A", "case-2", "medium", "Öl")
    client.put(
        "/api/v2/conversations/current/facts/medium",
        json={"wert": "Wasser"},
        params={"case_id": "case-2"},
        headers=auth("tok-A"),
    )
    assert (
        pipeline.memory.case_state(tenant_id="tenant-A", session_id="case-2")[0].wert
        == "Wasser"
    )
    # the token's OWN session (sess-A) must be untouched by an edit scoped to case-2
    assert pipeline.memory.case_state(tenant_id="tenant-A", session_id="sess-A") == ()
    client.delete(
        "/api/v2/conversations/current/facts/medium",
        params={"case_id": "case-2"},
        headers=auth("tok-A"),
    )
    assert pipeline.memory.case_state(tenant_id="tenant-A", session_id="case-2") == ()


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


def test_case_id_over_255_chars_is_a_clean_422_not_a_db_500():
    # 2026-07-04 audit finding: same gap as ChatRequest.case_id, but for the query-param form used
    # by every route in this file — an over-long value hit the DB's own String(255) column and
    # surfaced as a generic 500 instead of a validation error.
    client, _ = make_client()
    r = client.get(
        "/api/v2/conversations/current/memory",
        params={"case_id": "a" * 256},
        headers=auth("tok-A"),
    )
    assert r.status_code == 422


def test_case_id_at_exactly_255_chars_is_accepted():
    client, _ = make_client()
    r = client.get(
        "/api/v2/conversations/current/memory",
        params={"case_id": "a" * 255},
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
