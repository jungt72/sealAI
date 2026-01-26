
import pytest
from unittest.mock import MagicMock, patch
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

# We import the module to access hybrid_retrieve
from app.services.rag import rag_orchestrator

@pytest.fixture
def mock_qdrant_client():
    """Patches the global get_qdrant_client to return a Mock."""
    with patch("app.services.rag.rag_orchestrator.get_qdrant_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_embed():
    """Mocks default embedding to avoid loading models."""
    with patch("app.services.rag.rag_orchestrator._embed") as mock:
        mock.return_value = [[0.1] * 384]
        yield mock

def test_tenant_isolation_filter_logic(mock_qdrant_client, mock_embed):
    """
    Verify that correct 'any' filter is built for 'user-1'.
    User 'user-1' should see 'user-1' OR 'default'.
    """
    tenant = "user-1"
    
    # Mock search return to avoid crash
    mock_scored_point = MagicMock()
    mock_scored_point.payload = {"page_content": "foo", "metadata": {"tenant_id": "user-1"}}
    mock_scored_point.score = 0.9
    mock_qdrant_client.search.return_value = [mock_scored_point]

    # Act
    rag_orchestrator.hybrid_retrieve(query="test", tenant=tenant)

    # Assert
    # Verify search was called
    assert mock_qdrant_client.search.called
    
    # Inspect arguments
    call_kwargs = mock_qdrant_client.search.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    
    assert isinstance(query_filter, Filter)
    conditions = query_filter.must
    
    # We expect one condition for tenant_id using MatchAny
    tenant_condition = next(
        (c for c in conditions if c.key == "metadata.tenant_id"), None
    )
    assert tenant_condition is not None
    assert isinstance(tenant_condition.match, MatchAny)
    assert set(tenant_condition.match.any) == {"user-1", "default"}

def test_tenant_default_optimized_filter(mock_qdrant_client, mock_embed):
    """
    Verify that if tenant='default', we check ONLY 'default'.
    """
    tenant = "default"
    mock_qdrant_client.search.return_value = []

    rag_orchestrator.hybrid_retrieve(query="test", tenant=tenant)

    call_kwargs = mock_qdrant_client.search.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    
    tenant_condition = next(
        (c for c in query_filter.must if c.key == "metadata.tenant_id"), None
    )
    # expect strict MatchValue default
    assert isinstance(tenant_condition.match, MatchValue)
    assert tenant_condition.match.value == "default"

def test_kyrolon_retrieval_simulation(mock_qdrant_client, mock_embed):
    """
    Simulate Kyrolon return from Qdrant and ensure it is passed through.
    """
    # Create a mock ScoredPoint mimicking the SDK structure
    mock_pt = MagicMock()
    mock_pt.score = 0.95
    mock_pt.payload = {
        "page_content": "Kyrolon is a high-performance material...",
        "metadata": {
            "tenant_id": "default",
            "document_id": "doc-kyrolon",
            "source": "manual.pdf"
        }
    }
    mock_qdrant_client.search.return_value = [mock_pt]

    results = rag_orchestrator.hybrid_retrieve(query="Kyrolon", tenant="user-123")

    assert len(results) == 1
    doc = results[0]
    assert doc["metadata"]["tenant_id"] == "default"
    assert "Kyrolon" in doc["text"]

