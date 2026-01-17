import asyncio

import pytest

from app.langgraph_v2.utils import checkpointer as checkpointer_module


class _DummyPool:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls()


class _DummyRedis:
    def __init__(self, connection_pool):
        self.connection_pool = connection_pool


def test_checkpointer_env_namespace_key_prefix_applied(monkeypatch):
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_REDIS_URL", "redis://example:6379/0")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_NS", "consult.v1")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PREFIX", "lg:cp")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_TTL", "86400")

    captured = {}

    class FakeAsyncRedisSaver:
        def __init__(self, redis_client=None, namespace=None, key_prefix=None, ttl=None):
            captured["redis_client"] = redis_client
            captured["namespace"] = namespace
            captured["key_prefix"] = key_prefix
            captured["ttl"] = ttl

        async def asetup(self):
            return None

    monkeypatch.setattr(checkpointer_module, "AsyncRedisSaver", FakeAsyncRedisSaver)
    monkeypatch.setattr(checkpointer_module, "ConnectionPool", _DummyPool)
    monkeypatch.setattr(checkpointer_module, "Redis", _DummyRedis)
    monkeypatch.setattr(checkpointer_module, "make_async_redis_client", lambda *a, **kw: _DummyRedis(None))

    saver = asyncio.run(checkpointer_module.make_v2_checkpointer_async(require_async=True))

    assert isinstance(saver, FakeAsyncRedisSaver)
    assert captured["namespace"] == "consult.v1"
    assert captured["key_prefix"] == "lg:cp"
    assert captured["ttl"] == {"default_ttl": 1440.0}


def test_checkpointer_env_prefix_param_applied(monkeypatch):
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_REDIS_URL", "redis://example:6379/0")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_NS", "consult.v1")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PREFIX", "lg:cp")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_TTL", "86400")

    captured = {}

    class FakeAsyncRedisSaver:
        def __init__(self, redis_client=None, prefix=None, ttl_seconds=None):
            captured["redis_client"] = redis_client
            captured["prefix"] = prefix
            captured["ttl_seconds"] = ttl_seconds

        async def asetup(self):
            return None

    monkeypatch.setattr(checkpointer_module, "AsyncRedisSaver", FakeAsyncRedisSaver)
    monkeypatch.setattr(checkpointer_module, "ConnectionPool", _DummyPool)
    monkeypatch.setattr(checkpointer_module, "Redis", _DummyRedis)
    monkeypatch.setattr(checkpointer_module, "make_async_redis_client", lambda *a, **kw: _DummyRedis(None))

    saver = asyncio.run(checkpointer_module.make_v2_checkpointer_async(require_async=True))

    assert isinstance(saver, FakeAsyncRedisSaver)
    assert captured["prefix"] == "lg:cp:consult.v1"
    assert captured["ttl_seconds"] == 86400


def test_checkpointer_env_checkpoint_prefix_applied(monkeypatch):
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_REDIS_URL", "redis://example:6379/0")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_NS", "consult.v1")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PREFIX", "lg:cp")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_TTL", "86400")

    captured = {}

    class FakeAsyncRedisSaver:
        def __init__(
            self,
            redis_client=None,
            checkpoint_prefix=None,
            checkpoint_blob_prefix=None,
            checkpoint_write_prefix=None,
            ttl=None,
        ):
            captured["redis_client"] = redis_client
            captured["checkpoint_prefix"] = checkpoint_prefix
            captured["checkpoint_blob_prefix"] = checkpoint_blob_prefix
            captured["checkpoint_write_prefix"] = checkpoint_write_prefix
            captured["ttl"] = ttl

        async def asetup(self):
            return None

    monkeypatch.setattr(checkpointer_module, "AsyncRedisSaver", FakeAsyncRedisSaver)
    monkeypatch.setattr(checkpointer_module, "ConnectionPool", _DummyPool)
    monkeypatch.setattr(checkpointer_module, "Redis", _DummyRedis)
    monkeypatch.setattr(checkpointer_module, "make_async_redis_client", lambda *a, **kw: _DummyRedis(None))

    saver = asyncio.run(checkpointer_module.make_v2_checkpointer_async(require_async=True))

    assert isinstance(saver, FakeAsyncRedisSaver)
    assert captured["checkpoint_prefix"] == "lg:cp:consult.v1"
    assert captured["checkpoint_blob_prefix"] == "lg:cp:consult.v1:checkpoint_blob"
    assert captured["checkpoint_write_prefix"] == "lg:cp:consult.v1:checkpoint_write"
    assert captured["ttl"] == {"default_ttl": 1440.0}


def test_checkpointer_env_prefix_namespace_embedded_when_unsupported(monkeypatch):
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_REDIS_URL", "redis://example:6379/0")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_NS", "consult.v1")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PREFIX", "lg:cp")

    captured = {}

    class FakeAsyncRedisSaver:
        def __init__(self, redis_client=None, prefix=None, ttl_seconds=None, **kwargs):
            if "namespace" in kwargs or "checkpoint_ns" in kwargs:
                raise AssertionError("namespace should not be passed when unsupported")
            captured["redis_client"] = redis_client
            captured["prefix"] = prefix
            captured["ttl_seconds"] = ttl_seconds
            captured["kwargs"] = kwargs

        async def asetup(self):
            return None

    monkeypatch.setattr(checkpointer_module, "AsyncRedisSaver", FakeAsyncRedisSaver)
    monkeypatch.setattr(checkpointer_module, "ConnectionPool", _DummyPool)
    monkeypatch.setattr(checkpointer_module, "Redis", _DummyRedis)
    monkeypatch.setattr(checkpointer_module, "make_async_redis_client", lambda *a, **kw: _DummyRedis(None))

    saver = asyncio.run(checkpointer_module.make_v2_checkpointer_async(require_async=True))

    assert isinstance(saver, FakeAsyncRedisSaver)
    assert captured["prefix"] == "lg:cp:consult.v1"
    assert captured["kwargs"] == {}
