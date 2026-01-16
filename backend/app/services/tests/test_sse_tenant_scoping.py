
import pytest
import os
import asyncio
from unittest import mock
from app.services.sse_broadcast import SseBroadcastManager

def test_sse_broadcast_tenant_scoping():
    async def _test():
        mgr = SseBroadcastManager()
        # Mock the replay backend record_event to avoid Redis
        mgr._replay_backend.record_event = mock.AsyncMock(return_value=1)
        
        # 1. Subscribe with tenant
        queue = await mgr.subscribe(user_id="u1", chat_id="c1", tenant_id="t1")
        
        # Check internal subscribers key
        # Expected: ("t1:u1", "c1")
        assert ("t1:u1", "c1") in mgr._subscribers
        assert ("u1", "c1") not in mgr._subscribers

        # 2. Broadcast with tenant
        delivered = await mgr.broadcast(
            user_id="u1", 
            chat_id="c1", 
            tenant_id="t1", 
            event="test", 
            data={}
        )
        assert delivered == 1
        
        # 3. Verify backend call used scoped ID
        mgr._replay_backend.record_event.assert_called_with(
            user_id="t1:u1",
            chat_id="c1",
            event="test",
            data=mock.ANY,
            timestamp=mock.ANY
        )
    asyncio.run(_test())

def test_sse_broadcast_no_tenant_fallback():
    async def _test():
        mgr = SseBroadcastManager()
        mgr._replay_backend.record_event = mock.AsyncMock(return_value=1)
        
        await mgr.subscribe(user_id="u1", chat_id="c1")
        assert ("u1", "c1") in mgr._subscribers
        assert ("t1:u1", "c1") not in mgr._subscribers
    asyncio.run(_test())
