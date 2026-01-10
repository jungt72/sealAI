from __future__ import annotations

import asyncio
from weakref import WeakKeyDictionary

from app.services.jobs import queue as queue_module


def _run_in_loop(loop: asyncio.AbstractEventLoop, coro):
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)


def test_queue_client_scoped_to_event_loop(monkeypatch) -> None:
    created = []

    def fake_make_client(url: str):
        client = object()
        created.append((url, client))
        return client

    monkeypatch.setattr(queue_module, "make_async_redis_client", fake_make_client)
    monkeypatch.setattr(queue_module, "_QUEUE_STORE", WeakKeyDictionary())

    async def _get_client():
        return queue_module._queue_client()

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

    assert client_a is client_a_second
    assert client_a is not client_b
