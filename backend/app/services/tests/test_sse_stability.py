import pytest
import asyncio
import os
from app.services.sse_broadcast import RedisReplayBackend, MemoryReplayBackend

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

@pytest.mark.anyio
async def test_redis_sse_seq_stability():
    """
    Verify that RedisReplayBackend produces stable monotonic sequences even under trimming.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    if "redis" not in redis_url and "localhost" not in redis_url:
         pytest.skip("No local redis for stability test")
         
    # Use a small max_buffer to force trimming
    backend = RedisReplayBackend(redis_url=redis_url, max_buffer=3, ttl_sec=60)
    
    user_id = "test-user"
    chat_id = "test-chat-" + os.urandom(4).hex()
    tenant_id = "test-tenant"
    
    # 1. Record 3 events
    s1 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e1", data={}, tenant_id=tenant_id)
    s2 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e2", data={}, tenant_id=tenant_id)
    s3 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e3", data={}, tenant_id=tenant_id)
    
    assert s1 < s2 < s3
    
    # 2. Replay after s1
    records, miss = await backend.replay_after(user_id=user_id, chat_id=chat_id, last_seq=s1, tenant_id=tenant_id)
    assert len(records) == 2
    assert records[0].seq == s2
    assert records[1].seq == s3
    assert not miss

    # 3. Record one more event -> This should trigger LTRIM (max_buffer=3)
    # The list will now contain [e2, e3, e4]. e1 is gone.
    s4 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e4", data={}, tenant_id=tenant_id)
    assert s4 > s3
    
    # 4. Replay after s1 again -> should NOT show buffer miss because s2 is still there
    records, miss = await backend.replay_after(user_id=user_id, chat_id=chat_id, last_seq=s1, tenant_id=tenant_id)
    assert miss == False
    assert len(records) == 3
    assert records[0].seq == s2

    # 5. Record one more event -> Trims s2
    # List: [e3, e4, e5] with seqs [3, 4, 5]
    s5 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e5", data={}, tenant_id=tenant_id)
    
    # Replay after s1 -> NOW it should be a miss because s2 is gone. 
    # Client has 1, next available is 3. They missed 2.
    records, miss = await backend.replay_after(user_id=user_id, chat_id=chat_id, last_seq=s1, tenant_id=tenant_id)
    assert miss == True
    assert len(records) == 3
    assert records[0].seq == s3

    # 5. Replay after s2 -> no miss, return [e3, e4, e5]
    records, miss = await backend.replay_after(user_id=user_id, chat_id=chat_id, last_seq=s2, tenant_id=tenant_id)
    assert not miss
    assert len(records) == 3
    assert records[0].seq == s3
    assert records[1].seq == s4

@pytest.mark.anyio
async def test_memory_sse_seq_stability():
    """Verify memory backend also handles stable seq (it always did but good to check)."""
    backend = MemoryReplayBackend(max_buffer=2)
    user_id = "u1"
    chat_id = "c1"
    
    s1 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e1", data={})
    s2 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e1", data={})
    s3 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e1", data={}) # Trims s1
    
    # Replay after s1: next is s2=2. s2 is available. No miss.
    records, miss = await backend.replay_after(user_id=user_id, chat_id=chat_id, last_seq=s1)
    assert miss == False
    
    # Record s4: trims s2
    s4 = await backend.record_event(user_id=user_id, chat_id=chat_id, event="e4", data={})
    
    # Replay after s1: next is 2. 2 is gone. Miss!
    records, miss = await backend.replay_after(user_id=user_id, chat_id=chat_id, last_seq=s1)
    assert miss == True
