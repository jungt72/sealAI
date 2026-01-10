from __future__ import annotations

import asyncio
from weakref import WeakKeyDictionary

from app.services import sse_broadcast as sse_module


def _run_in_loop(loop: asyncio.AbstractEventLoop, coro):
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)


def test_sse_manager_scoped_to_event_loop(monkeypatch) -> None:
    monkeypatch.setattr(sse_module, "_SSE_MANAGER_STORE", WeakKeyDictionary())

    async def _get_manager():
        return sse_module.get_sse_broadcast()

    loop_a = asyncio.new_event_loop()
    try:
        manager_a = _run_in_loop(loop_a, _get_manager())
        manager_a_second = _run_in_loop(loop_a, _get_manager())
    finally:
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        manager_b = _run_in_loop(loop_b, _get_manager())
    finally:
        loop_b.close()

    assert manager_a is manager_a_second
    assert manager_a is not manager_b


def test_redis_replay_backend_client_scoped_to_event_loop(monkeypatch) -> None:
    created = []

    def fake_make_client(url: str, *, decode_responses: bool = False):
        client = object()
        created.append((url, decode_responses, client))
        return client

    monkeypatch.setattr(sse_module, "Redis", object())
    monkeypatch.setattr(sse_module, "make_async_redis_client", fake_make_client)

    backend = sse_module.RedisReplayBackend(
        redis_url="redis://example:6379/0",
        max_buffer=2,
        ttl_sec=10,
        fallback=sse_module.MemoryReplayBackend(),
    )

    async def _get_client():
        return await backend._get_client()

    loop_a = asyncio.new_event_loop()
    try:
        client_a = _run_in_loop(loop_a, _get_client())
        client_a_second = _run_in_loop(loop_a, _get_client())
    finally:
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        client_b = _run_in_loop(loop_b, _get_client())
    finally:
        loop_b.close()

    assert len(created) == 2
    assert created[0][0] == "redis://example:6379/0"
    assert created[0][1] is True
    assert client_a is client_a_second
    assert client_a is not client_b
