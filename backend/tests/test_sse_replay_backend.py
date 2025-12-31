import os

from app.services import sse_broadcast as module
from app.services.sse_broadcast import MemoryReplayBackend, RedisReplayBackend


def test_build_replay_backend_defaults_to_memory(monkeypatch):
    monkeypatch.delenv("SEALAI_SSE_REPLAY_BACKEND", raising=False)
    backend = module.build_replay_backend()
    assert isinstance(backend, MemoryReplayBackend)


def test_build_replay_backend_redis_selected(monkeypatch):
    monkeypatch.setenv("SEALAI_SSE_REPLAY_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    backend = module.build_replay_backend()
    if module.Redis is None:
        assert isinstance(backend, MemoryReplayBackend)
    else:
        assert isinstance(backend, RedisReplayBackend)


def test_build_replay_backend_redis_fallback_when_missing_url(monkeypatch):
    monkeypatch.setenv("SEALAI_SSE_REPLAY_BACKEND", "redis")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("LANGGRAPH_V2_REDIS_URL", raising=False)
    monkeypatch.delenv("redis_url", raising=False)
    backend = module.build_replay_backend()
    assert isinstance(backend, MemoryReplayBackend)
