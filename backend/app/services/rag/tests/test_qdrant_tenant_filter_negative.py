import pytest
from app.services.rag.rag_orchestrator import hybrid_retrieve

@pytest.mark.asyncio
async def test_hybrid_retrieve_enforces_tenant_id():
    """Verify hybrid_retrieve raises error if tenant is missing."""
    
    with pytest.raises(ValueError, match="Tenant ID is required"):
        hybrid_retrieve(query="test", tenant=None)
