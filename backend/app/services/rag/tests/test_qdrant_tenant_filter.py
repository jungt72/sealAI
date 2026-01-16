
import os
import pytest
from unittest import mock
from typing import Any
from qdrant_client import models

# IMPORTANT: Set env vars BEFORE importing app modules to pass Settings validation
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "password"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_DB"] = "sealai"
os.environ["OPENAI_API_KEY"] = "sk-dummy"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["QDRANT_COLLECTION"] = "sealai-docs"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["NEXTAUTH_URL"] = "http://localhost:3000"
os.environ["NEXTAUTH_SECRET"] = "secret"
os.environ["KEYCLOAK_ISSUER"] = "http://localhost:8080"
os.environ["KEYCLOAK_JWKS_URL"] = "http://localhost:8080/jwks"
os.environ["KEYCLOAK_CLIENT_ID"] = "sealai"
os.environ["KEYCLOAK_CLIENT_SECRET"] = "secret"
os.environ["KEYCLOAK_EXPECTED_AZP"] = "sealai"
os.environ["RAG_SEARCH_ENABLED"] = "1"

# Import modules to test
from app.services.rag import qdrant_naming
from app.services.rag import rag_orchestrator
from app.services.memory import memory_core

def test_qdrant_collection_name_strict_single():
    """Verify strictly ignores tenant_id in collection naming."""
    name = qdrant_naming.qdrant_collection_name(
        base="sealai-docs", prefix="rag", tenant_id="tenant-1"
    )
    # MUST return base only (or prefix:base) but NOT tenant
    # Our patch returns "sealai-docs" (clean_base)
    assert name == "sealai-docs"
    
    name_empty = qdrant_naming.qdrant_collection_name(
        base="sealai-docs", prefix=None, tenant_id=None
    )
    assert name_empty == "sealai-docs"

def test_memory_core_ltm_export_filter():
    """Verify ltm_export_all enforces tenant_id filter."""
    with mock.patch("app.services.memory.memory_core._get_qdrant_client") as mock_get_client:
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.scroll.return_value = ([], None)
        
        # Call with tenant_id
        memory_core.ltm_export_all(
            user="user1", chat_id="chat1", tenant_id="tenantA", limit=10
        )
        
        # Verify scroll_filter passed to client.scroll
        args, kwargs = mock_client.scroll.call_args
        scroll_filter = kwargs.get("scroll_filter")
        
        assert isinstance(scroll_filter, models.Filter)
        # Check must conditions
        must = scroll_filter.must
        # We expect user, chat_id, AND tenant_id
        found_tenant = False
        for cond in must:
            if isinstance(cond, models.FieldCondition) and cond.key == "tenant_id":
                if cond.match.value == "tenantA":
                    found_tenant = True
        
        assert found_tenant, "tenant_id filter NOT found in ltm_export_all scroll"

def test_rag_orchestrator_hybrid_retrieve_filter():
    """Verify hybrid_retrieve enforces tenant_id in metadata_filters."""
    # We mock _qdrant_search_with_retry to see what filters it gets
    with mock.patch("app.services.rag.rag_orchestrator._qdrant_search_with_retry") as mock_search:
        mock_search.return_value = ([], {}) # vec_hits, meta
        
        # Mock _embed to avoid model loading
        with mock.patch("app.services.rag.rag_orchestrator._embed") as mock_embed:
            mock_embed.return_value = [[0.1]*10] # dummy vector
            
            # Call hybrid_retrieve with tenant
            rag_orchestrator.hybrid_retrieve(
                query="test", tenant="tenantB"
            )
            
            # Verify call
            args, kwargs = mock_search.call_args
            # _qdrant_search_with_retry(vec, collection, top_k=..., metadata_filters=...)
            filters = kwargs.get("metadata_filters")
            
            assert filters is not None
            assert filters.get("tenant_id") == "tenantB"
