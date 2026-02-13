from __future__ import annotations

import pytest

from app.langgraph_v2.constants import CHECKPOINTER_NAMESPACE_V2
from app.langgraph_v2.sealai_graph_v2 import build_v2_config
from app.langgraph_v2.utils import checkpointer as cp


class _DummyPool:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return object()


class _DummyRedis:
    def __init__(self, connection_pool=None):
        self.connection_pool = connection_pool


class _DummySaver:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def asetup(self):
        return None


class _FailingSaver:
    def __init__(self, **_kwargs):
        pass

    async def asetup(self):
        raise RuntimeError("redis init failed")


@pytest.mark.anyio
async def test_v2_checkpointer_uses_strict_v2_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER_TTL_SECONDS", "120")

    captured: dict[str, object] = {}

    class _CaptureSaver(_DummySaver):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(cp, "ConnectionPool", _DummyPool)
    monkeypatch.setattr(cp, "Redis", _DummyRedis)
    monkeypatch.setattr(cp, "AsyncRedisSaver", _CaptureSaver)

    saver = await cp.make_v2_checkpointer_async()

    assert isinstance(saver, _CaptureSaver)
    assert captured["checkpoint_prefix"] == "sealai:v2:checkpoint"
    assert captured["checkpoint_blob_prefix"] == "sealai:v2:checkpoint_blob"
    assert captured["checkpoint_write_prefix"] == "sealai:v2:checkpoint_write"
    assert captured["ttl"] == {"default_ttl": 2}


@pytest.mark.anyio
async def test_v2_checkpointer_fails_fast_when_redis_init_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", raising=False)

    monkeypatch.setattr(cp, "ConnectionPool", _DummyPool)
    monkeypatch.setattr(cp, "Redis", _DummyRedis)
    monkeypatch.setattr(cp, "AsyncRedisSaver", _FailingSaver)

    with pytest.raises(RuntimeError, match="memory fallback is disabled"):
        await cp.make_v2_checkpointer_async()


def test_v2_config_always_sets_non_empty_sealai_namespace() -> None:
    config = build_v2_config(thread_id="chat-1", user_id="user-1", tenant_id="tenant-1")
    checkpoint_ns = config["configurable"]["checkpoint_ns"]

    assert CHECKPOINTER_NAMESPACE_V2 == "sealai:v2:"
    assert checkpoint_ns == "sealai:v2:"
    assert checkpoint_ns != ""
    assert checkpoint_ns != "__empty__"
