import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import redis_client as redis_client_module
from app.services.jobs import queue as queue_module


def test_enqueue_job_trims_queue(monkeypatch) -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.rpush = AsyncMock()
            self.ltrim = AsyncMock()

    client = DummyClient()
    monkeypatch.setattr(queue_module, "_queue_client", lambda: client)

    asyncio.run(queue_module.enqueue_job("jobs:chat_transcripts", {"hello": "world"}))

    client.rpush.assert_awaited_once()
    client.ltrim.assert_awaited_once_with(
        "jobs:chat_transcripts",
        -queue_module.MAX_JOBS_QUEUE_LEN,
        -1,
    )


def test_queue_client_uses_shared_pool_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_from_url(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    class DummyRedis:
        def __init__(self, connection_pool: object) -> None:
            captured["pool"] = connection_pool

    monkeypatch.setattr(
        redis_client_module,
        "ConnectionPool",
        SimpleNamespace(from_url=fake_from_url),
    )
    monkeypatch.setattr(redis_client_module, "Redis", DummyRedis)
    monkeypatch.setattr(redis_client_module, "DEFAULT_REDIS_MAX_CONNECTIONS", 42)
    monkeypatch.setattr(redis_client_module, "DEFAULT_REDIS_SOCKET_TIMEOUT", 1.5)
    monkeypatch.setattr(redis_client_module, "DEFAULT_REDIS_SOCKET_CONNECT_TIMEOUT", 2.5)
    monkeypatch.setattr(redis_client_module, "DEFAULT_REDIS_HEALTH_CHECK_INTERVAL", 17)
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")

    queue_module._queue_client.cache_clear()
    client = queue_module._queue_client()

    assert isinstance(client, DummyRedis)
    assert captured["url"] == "redis://example:6379/0"
    assert captured["kwargs"] == {
        "max_connections": 42,
        "socket_timeout": 1.5,
        "socket_connect_timeout": 2.5,
        "retry_on_timeout": True,
        "health_check_interval": 17,
        "decode_responses": False,
    }
