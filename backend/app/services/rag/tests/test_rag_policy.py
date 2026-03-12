import pytest
from typing import Any, Dict, List, Optional
from app.services.rag.rag_orchestrator import _build_qdrant_filter, RAG_SHARED_TENANT_ID, RAG_VISIBILITY_PUBLIC

def test_build_qdrant_filter_tenant_only():
    # Only tenant_id, no visibility enforcement
    filters = {"tenant_id": "tenant-1"}
    q_filter = _build_qdrant_filter(filters)
    
    assert q_filter == {
        "must": [
            {"key": "tenant_id", "match": {"value": "tenant-1"}}
        ]
    }

def test_build_qdrant_filter_with_visibility():
    # tenant_id + visibility user id (standard user flow)
    filters = {
        "tenant_id": ["tenant-1", RAG_SHARED_TENANT_ID],
        "_visibility_user_id": "tenant-1"
    }
    q_filter = _build_qdrant_filter(filters)
    
    assert q_filter["must"] == [
        {"key": "tenant_id", "match": {"any": ["tenant-1", RAG_SHARED_TENANT_ID]}}
    ]
    assert q_filter["should"] == [
        {"key": "visibility", "match": {"value": RAG_VISIBILITY_PUBLIC}},
        {"key": "tenant_id", "match": {"value": "tenant-1"}}
    ]

def test_build_qdrant_filter_multi_tenant():
    filters = {"tenant_id": ["t1", "t2"]}
    q_filter = _build_qdrant_filter(filters)
    assert q_filter["must"] == [{"key": "tenant_id", "match": {"any": ["t1", "t2"]}}]


def test_build_qdrant_filter_applies_supported_metadata_filters():
    filters = {
        "tenant_id": ["tenant-1", RAG_SHARED_TENANT_ID],
        "_visibility_user_id": "tenant-1",
        "route_key": "standard_or_norm",
        "category": "norms",
        "source_system": "paperless",
        "tags": ["norm", "knowledge"],
    }
    q_filter = _build_qdrant_filter(filters)

    must = q_filter["must"]
    assert {"key": "metadata.route_key", "match": {"value": "standard_or_norm"}} in must
    assert {"key": "metadata.category", "match": {"value": "norms"}} in must
    assert {"key": "metadata.source_system", "match": {"value": "paperless"}} in must
    assert {"key": "metadata.tags", "match": {"any": ["norm", "knowledge"]}} in must

@pytest.mark.parametrize("tenant,expected_tenants", [
    ("user-1", ["user-1", RAG_SHARED_TENANT_ID]),
    (RAG_SHARED_TENANT_ID, [RAG_SHARED_TENANT_ID]),
    (None, [])
])
def test_hybrid_retrieve_filter_logic_unit(tenant, expected_tenants, monkeypatch):
    """Verify how hybrid_retrieve prepares filters for _build_qdrant_filter."""
    # We mock everything to avoid side effects
    captured_filters = {}
    
    def mock_build_filter(filters):
        nonlocal captured_filters
        captured_filters = filters
        return None
        
    monkeypatch.setattr("app.services.rag.rag_orchestrator._build_qdrant_filter", mock_build_filter)
    monkeypatch.setattr("app.services.rag.rag_orchestrator._embed", lambda x: [[0.1]*128])
    monkeypatch.setattr("app.services.rag.rag_orchestrator._embed_sparse_query", lambda x: None)
    monkeypatch.setattr("app.services.rag.rag_orchestrator._qdrant_search_with_retry", lambda *args, **kwargs: ([], {}))
    
    from app.services.rag.rag_orchestrator import hybrid_retrieve
    
    hybrid_retrieve(query="test", tenant=tenant)
    
    if tenant:
        assert "tenant_id" in captured_filters
        actual_tenants = captured_filters["tenant_id"]
        if isinstance(actual_tenants, str):
            actual_tenants = [actual_tenants]
        assert sorted(actual_tenants) == sorted(expected_tenants)
        
        if tenant != RAG_SHARED_TENANT_ID:
            assert captured_filters["_visibility_user_id"] == tenant
        else:
            assert "_visibility_user_id" not in captured_filters
    else:
        assert "_visibility_user_id" not in captured_filters


def test_hybrid_retrieve_preserves_supported_metadata_filters(monkeypatch):
    captured_filters = {}

    def mock_build_filter(filters):
        nonlocal captured_filters
        captured_filters = dict(filters or {})
        return None

    monkeypatch.setattr("app.services.rag.rag_orchestrator._build_qdrant_filter", mock_build_filter)
    monkeypatch.setattr("app.services.rag.rag_orchestrator._embed", lambda x: [[0.1] * 128])
    monkeypatch.setattr("app.services.rag.rag_orchestrator._embed_sparse_query", lambda x: None)
    monkeypatch.setattr("app.services.rag.rag_orchestrator._qdrant_search_with_retry", lambda *args, **kwargs: ([], {}))

    from app.services.rag.rag_orchestrator import hybrid_retrieve

    hybrid_retrieve(
        query="test",
        tenant="tenant-1",
        metadata_filters={
            "route_key": "standard_or_norm",
            "category": "norms",
            "source_system": "paperless",
            "tags": ["norm", "knowledge"],
            "unsupported_key": "ignored",
        },
        use_rerank=False,
    )

    assert captured_filters["tenant_id"] == ["tenant-1", RAG_SHARED_TENANT_ID]
    assert captured_filters["route_key"] == "standard_or_norm"
    assert captured_filters["category"] == "norms"
    assert captured_filters["source_system"] == "paperless"
    assert captured_filters["tags"] == ["norm", "knowledge"]
    assert "unsupported_key" not in captured_filters
