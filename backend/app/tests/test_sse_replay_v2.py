import pytest
import os
import uuid
import asyncio
from app.services.sse_broadcast import RedisReplayBackend
from app.services.redis_client import make_async_redis_client

# Helper to check Redis availability
async def is_redis_available(url: str) -> bool:
    try:
        # decode_responses=True match usage in sse_broadcast
        client = make_async_redis_client(url, decode_responses=True)
        await client.ping()
        # redis-py asyncio: close() is deprecated -> use aclose()
        await client.aclose()
        return True
    except Exception:
        return False


@pytest.mark.asyncio
class TestSSEReplayV2:
    """
    Validates SSE Replay Backend strictly against V2 Specs:
    1. Tenant Isolation
    2. Monotonicity
    3. Replay Accuracy
    """

    async def get_backend(self, max_buffer: int = 50):
        url = os.getenv("REDIS_URL") or os.getenv("REDIS_DSN") or "redis://localhost:6379/0"
        if not await is_redis_available(url):
            pytest.skip(f"Redis not available at {url}")

        # Use a short TTL for tests to avoid clutter
        return RedisReplayBackend(redis_url=url, max_buffer=max_buffer, ttl_sec=60)

    async def test_tenant_isolation(self):
        backend = await self.get_backend()

        # Identical user/chat, but different tenants
        u1, c1 = "user-iso", str(uuid.uuid4())
        t1, t2 = "tenant-A", "tenant-B"

        # Tenant A writes
        await backend.record_event(
            user_id=u1, chat_id=c1, tenant_id=t1,
            event="msg", data={"val": "A"}
        )

        # Tenant B writes
        await backend.record_event(
            user_id=u1, chat_id=c1, tenant_id=t2,
            event="msg", data={"val": "B"}
        )

        # Replay A -> Should see A only
        recs_a, _ = await backend.replay_after(
            user_id=u1, chat_id=c1, tenant_id=t1, last_seq=0
        )
        assert len(recs_a) >= 1
        assert all(r.tenant_id == t1 for r in recs_a)
        assert recs_a[-1].data["val"] == "A"

        # Replay B -> Should see B only
        recs_b, _ = await backend.replay_after(
            user_id=u1, chat_id=c1, tenant_id=t2, last_seq=0
        )
        assert len(recs_b) >= 1
        assert all(r.tenant_id == t2 for r in recs_b)
        assert recs_b[-1].data["val"] == "B"

    async def test_monotonicity_and_replay(self):
        backend = await self.get_backend()
        t1, u1, c1 = "tenant-Seq", "user-Seq", str(uuid.uuid4())

        # Record sequence
        expected_seqs = []
        for i in range(1, 6):
            seq = await backend.record_event(
                user_id=u1, chat_id=c1, tenant_id=t1,
                event="update", data={"i": i}
            )
            expected_seqs.append(seq)
            # Ensure strictly increasing
            if i > 1:
                assert seq > expected_seqs[-2]

        # Full Replay
        recs, miss = await backend.replay_after(
            user_id=u1, chat_id=c1, tenant_id=t1, last_seq=0
        )
        assert not miss
        assert len(recs) == 5
        assert [r.seq for r in recs] == expected_seqs
        assert [r.data["i"] for r in recs] == [1, 2, 3, 4, 5]

        # Partial Replay (from 3rd event)
        cutoff_seq = expected_seqs[2]  # seq of 3rd event
        recs_partial, miss_p = await backend.replay_after(
            user_id=u1, chat_id=c1, tenant_id=t1, last_seq=cutoff_seq
        )
        assert not miss_p
        assert len(recs_partial) == 2
        assert [r.data["i"] for r in recs_partial] == [4, 5]

    async def test_gap_detection(self):
        # Create a backend with tiny buffer to force eviction
        backend = await self.get_backend(max_buffer=2)

        t1, u1, c1 = "tenant-Gap", "user-Gap", str(uuid.uuid4())

        # Write 5 events (store only last 2)
        s1 = await backend.record_event(user_id=u1, chat_id=c1, tenant_id=t1, event="e", data={"n": 1})
        await backend.record_event(user_id=u1, chat_id=c1, tenant_id=t1, event="e", data={"n": 2})
        await backend.record_event(user_id=u1, chat_id=c1, tenant_id=t1, event="e", data={"n": 3})
        s4 = await backend.record_event(user_id=u1, chat_id=c1, tenant_id=t1, event="e", data={"n": 4})
        s5 = await backend.record_event(user_id=u1, chat_id=c1, tenant_id=t1, event="e", data={"n": 5})

        # Request from way back (s1) -> Should miss
        recs, miss = await backend.replay_after(
            user_id=u1, chat_id=c1, tenant_id=t1, last_seq=s1
        )

        # Redis List now has [4, 5] due to max_buffer=2
        assert miss is True

        # Should return what is available
        assert len(recs) == 2
        assert recs[0].seq == s4
        assert recs[1].seq == s5
        # Optional stronger assertions:
        assert recs[0].data["n"] == 4
        assert recs[1].data["n"] == 5
