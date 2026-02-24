"""Tests for H3: Visibility filter enforcement in _build_qdrant_filter()."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _build_qdrant_filter — unit tests
# ---------------------------------------------------------------------------

def test_no_filters_returns_none():
    from app.services.rag.rag_orchestrator import _build_qdrant_filter

    assert _build_qdrant_filter(None) is None
    assert _build_qdrant_filter({}) is None


def test_tenant_filter_single():
    from app.services.rag.rag_orchestrator import _build_qdrant_filter

    result = _build_qdrant_filter({"tenant_id": "acme"})
    assert result is not None
    must = result["must"]
    assert len(must) == 1
    assert must[0]["key"] == "tenant_id"
    assert must[0]["match"]["value"] == "acme"


def test_tenant_filter_multi():
    from app.services.rag.rag_orchestrator import _build_qdrant_filter

    result = _build_qdrant_filter({"tenant_id": ["acme", "sealai"]})
    assert result is not None
    must = result["must"]
    assert must[0]["match"]["any"] == ["acme", "sealai"]


def test_visibility_user_id_adds_should_clause():
    """When _visibility_user_id is set, a should-clause must be added."""
    from app.services.rag.rag_orchestrator import _build_qdrant_filter

    result = _build_qdrant_filter({
        "tenant_id": ["user-123", "sealai"],
        "_visibility_user_id": "user-123",
    })
    assert result is not None

    # must-clause: tenant scoping
    assert "must" in result
    # should-clause: visibility gate
    assert "should" in result

    should = result["should"]
    should_keys = [c["key"] for c in should]
    should_values = [c["match"]["value"] for c in should]

    assert "visibility" in should_keys
    assert "public" in should_values
    assert "tenant_id" in should_keys
    assert "user-123" in should_values


def test_visibility_gate_not_added_without_user_id():
    """Without _visibility_user_id the filter must NOT have a should-clause."""
    from app.services.rag.rag_orchestrator import _build_qdrant_filter

    result = _build_qdrant_filter({"tenant_id": "acme"})
    assert result is not None
    assert "should" not in result


def test_visibility_user_id_key_not_leaked_as_qdrant_field():
    """_visibility_user_id must not appear as a Qdrant must/should field key."""
    from app.services.rag.rag_orchestrator import _build_qdrant_filter

    result = _build_qdrant_filter({
        "tenant_id": "user-x",
        "_visibility_user_id": "user-x",
    })
    assert result is not None

    all_keys = [c.get("key", "") for clause_list in result.values() for c in clause_list]
    assert "_visibility_user_id" not in all_keys


# ---------------------------------------------------------------------------
# hybrid_retrieve — visibility propagation integration test
# ---------------------------------------------------------------------------

def test_hybrid_retrieve_injects_visibility_user_id(monkeypatch: pytest.MonkeyPatch):
    """hybrid_retrieve must pass _visibility_user_id to _build_qdrant_filter."""
    from app.services.rag import rag_orchestrator as ro

    captured_filters: list[dict] = []

    original_build = ro._build_qdrant_filter

    def patched_build(filters=None):
        if filters:
            captured_filters.append(dict(filters))
        return original_build(filters)

    monkeypatch.setattr(ro, "_build_qdrant_filter", patched_build)
    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0] * 4])
    monkeypatch.setattr(ro, "_embed_sparse_query", lambda _q: None)
    monkeypatch.setattr(
        ro,
        "_qdrant_search_with_retry",
        lambda *a, **kw: ([], {"attempts": 1, "timeout_s": 5.0, "elapsed_ms": 1,
                                "retry_backoff_ms": None, "error": None}),
    )
    monkeypatch.setattr(ro, "_bm25_search", lambda *a, **kw: ([], None))
    monkeypatch.setattr(ro, "_fallback_external_search", lambda *a, **kw: [])
    monkeypatch.setattr(ro, "USE_BM25", False)

    ro.hybrid_retrieve(
        query="PTFE Dichtung",
        tenant="user-42",
        user_id="user-42",
        k=3,
        use_rerank=False,
    )

    # At least one call to _build_qdrant_filter should carry _visibility_user_id
    matching = [f for f in captured_filters if "_visibility_user_id" in f]
    assert matching, "Expected _visibility_user_id to be present in filter call"
    assert matching[0]["_visibility_user_id"] == "user-42"


def test_hybrid_retrieve_visibility_falls_back_to_tenant(monkeypatch: pytest.MonkeyPatch):
    """When user_id is omitted, tenant acts as the visibility user id."""
    from app.services.rag import rag_orchestrator as ro

    captured_filters: list[dict] = []

    original_build = ro._build_qdrant_filter

    def patched_build(filters=None):
        if filters:
            captured_filters.append(dict(filters))
        return original_build(filters)

    monkeypatch.setattr(ro, "_build_qdrant_filter", patched_build)
    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0] * 4])
    monkeypatch.setattr(ro, "_embed_sparse_query", lambda _q: None)
    monkeypatch.setattr(
        ro,
        "_qdrant_search_with_retry",
        lambda *a, **kw: ([], {"attempts": 1, "timeout_s": 5.0, "elapsed_ms": 1,
                                "retry_backoff_ms": None, "error": None}),
    )
    monkeypatch.setattr(ro, "_bm25_search", lambda *a, **kw: ([], None))
    monkeypatch.setattr(ro, "_fallback_external_search", lambda *a, **kw: [])
    monkeypatch.setattr(ro, "USE_BM25", False)

    ro.hybrid_retrieve(
        query="NBR O-Ring",
        tenant="tenant-99",
        # user_id omitted → falls back to tenant
        k=2,
        use_rerank=False,
    )

    matching = [f for f in captured_filters if "_visibility_user_id" in f]
    assert matching
    assert matching[0]["_visibility_user_id"] == "tenant-99"
