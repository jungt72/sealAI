import asyncio

import pytest

from app.services.sse_broadcast import MemoryReplayBackend, SseBroadcastManager


def test_sse_broadcast_subscribe_broadcast_unsubscribe() -> None:
    manager = SseBroadcastManager(
        replay_backend=MemoryReplayBackend(max_buffer=10),
        queue_maxsize=10,
        slow_notice_interval=0.0,
    )

    async def _run() -> None:
        queue = await manager.subscribe(user_id="user-1", chat_id="chat-1")
        delivered = await manager.broadcast(
            user_id="user-1",
            chat_id="chat-1",
            event="parameter_patch_ack",
            data={"chat_id": "chat-1"},
        )
        assert delivered == 1
        seq, event_name, payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert seq == 1
        assert event_name == "parameter_patch_ack"
        assert payload["chat_id"] == "chat-1"

        await manager.unsubscribe(user_id="user-1", chat_id="chat-1", queue=queue)
        delivered = await manager.broadcast(
            user_id="user-1",
            chat_id="chat-1",
            event="parameter_patch_ack",
            data={"chat_id": "chat-1"},
        )
        assert delivered == 0
        with pytest.raises(asyncio.QueueEmpty):
            queue.get_nowait()

    asyncio.run(_run())


def test_sse_replay_returns_buffered_events() -> None:
    manager = SseBroadcastManager(
        replay_backend=MemoryReplayBackend(max_buffer=5),
        queue_maxsize=5,
        slow_notice_interval=0.0,
    )

    async def _run() -> None:
        for seq in range(1, 6):
            await manager.record_event(
                user_id="user-1",
                chat_id="chat-1",
                event="token",
                data={"seq": seq},
                timestamp=100.0 + seq,
            )
        replay, buffer_miss = await manager.replay_after(
            user_id="user-1",
            chat_id="chat-1",
            last_seq=3,
        )
        assert buffer_miss is False
        assert [item["seq"] for item in replay] == [4, 5]

    asyncio.run(_run())


def test_sse_replay_buffer_miss_emits_resync() -> None:
    manager = SseBroadcastManager(
        replay_backend=MemoryReplayBackend(max_buffer=3),
        queue_maxsize=5,
        slow_notice_interval=0.0,
    )

    async def _run() -> None:
        for seq in range(1, 4):
            await manager.record_event(
                user_id="user-1",
                chat_id="chat-1",
                event="token",
                data={"seq": seq},
                timestamp=100.0 + seq,
            )
        replay, buffer_miss = await manager.replay_after(
            user_id="user-1",
            chat_id="chat-1",
            last_seq=0,
        )
        assert replay == []
        assert buffer_miss is True

    asyncio.run(_run())


def test_sse_backpressure_drops_oldest_and_marks_slow() -> None:
    manager = SseBroadcastManager(
        replay_backend=MemoryReplayBackend(max_buffer=5),
        queue_maxsize=2,
        slow_notice_interval=0.0,
    )

    async def _run() -> None:
        queue = await manager.subscribe(user_id="user-1", chat_id="chat-1")
        await manager.broadcast(
            user_id="user-1",
            chat_id="chat-1",
            event="token",
            data={"seq": 1},
        )
        await manager.broadcast(
            user_id="user-1",
            chat_id="chat-1",
            event="token",
            data={"seq": 2},
        )
        await manager.broadcast(
            user_id="user-1",
            chat_id="chat-1",
            event="token",
            data={"seq": 3},
        )
        first = queue.get_nowait()
        second = queue.get_nowait()
        assert {first[1], second[1]} == {"token", "slow_client"}
        assert any(item[1] == "token" and item[2]["seq"] == 3 for item in (first, second))

    asyncio.run(_run())
