import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.sse_broadcast import SseBroadcastManager, _SseBroadcastProxy

@pytest.mark.asyncio
async def test_sse_broadcast_keys_contain_tenant():
    """Verify that Redis keys are scoped by tenant."""
    # Setup
    manager = SseBroadcastManager(redis_url="redis://localhost:6379/0")
    
    # We mock the Redis client to inspect calls
    mock_redis = AsyncMock()
    manager._redis = mock_redis
    
    tenant_id = "tenantA"
    chat_id = "chat123"
    
    # Action: record event
    # Note: record_event signature might need update or we check internal helper if patched
    # Currently sse_broadcast uses chat_id only. We WANT it to use tenant_id.
    # We simulate passing tenant_id via method (if we update it) or we rely on chat_id being composite?
    # NO, design goal is explicit tenant_id arg or extraction.
    
    # Let's assume we patch record_event to accept tenant_id
    # await manager.record_event(tenant_id=tenant_id, chat_id=chat_id, event="test", data={})
    
    # FOR NOW: Check strictly that the KEY GENERATION Strategy changes.
    # We can test the helper method _get_redis_key if we can access it, or mock internal calls.
    
    key = manager._get_redis_key(chat_id, tenant_id) # Future signature
    assert f"sse:events:{tenant_id}:{chat_id}" in key or f"sse:events:{tenant_id}/{chat_id}" in key

@pytest.mark.asyncio
async def test_sse_broadcast_channels_isolation():
    """Tenant A and Tenant B with same chat_id must have different channels."""
    manager = SseBroadcastManager("redis://fake")
    
    channel_a = manager._get_redis_channel("chatX", "tenantA")
    channel_b = manager._get_redis_channel("chatX", "tenantB")
    
    assert channel_a != channel_b
    assert "tenantA" in channel_a
    assert "tenantB" in channel_b
