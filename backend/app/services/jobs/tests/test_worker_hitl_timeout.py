from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timezone

import pytest

os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost")
os.environ.setdefault("nextauth_secret", "test")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub

from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id
from app.services.jobs import worker


class FakeRedis:
    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}

    async def zrevrange(self, key: str, _start: int, _stop: int):
        bucket = self.zsets.get(key) or {}
        ordered = sorted(bucket.items(), key=lambda item: item[1], reverse=True)
        return [member for member, _score in ordered]


class _Snapshot:
    def __init__(self, values):
        self.values = values


class _FakeGraph:
    def __init__(self, states: dict[str, dict]):
        self.states = states

    async def aget_state(self, config):
        thread_id = (config.get("configurable") or {}).get("thread_id")
        return _Snapshot(self.states.get(thread_id, {}))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_hitl_timeout_job_rejects_old_pending_and_respects_tenant_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_ts = datetime(2026, 2, 17, 12, 0, tzinfo=timezone.utc).timestamp()
    old_created_at = datetime.fromtimestamp(now_ts - (5 * 3600), tz=timezone.utc).isoformat().replace("+00:00", "Z")

    chat_id = "chat-shared"
    owner_id = "user-1"
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"
    thread_a = resolve_checkpoint_thread_id(tenant_id=tenant_a, user_id=owner_id, chat_id=chat_id)
    thread_b = resolve_checkpoint_thread_id(tenant_id=tenant_b, user_id=owner_id, chat_id=chat_id)

    graph = _FakeGraph(
        {
            thread_a: {
                "awaiting_user_confirmation": True,
                "confirm_status": "pending",
                "confirm_checkpoint": {
                    "checkpoint_id": "chk-a",
                    "conversation_id": thread_a,
                    "required_user_sub": owner_id,
                    "created_at": old_created_at,
                },
                "policy_report": {},
            },
            thread_b: {
                "awaiting_user_confirmation": True,
                "confirm_status": "pending",
                "confirm_checkpoint": {
                    "checkpoint_id": "chk-b",
                    "conversation_id": thread_b,
                    "required_user_sub": "user-2",
                    "created_at": old_created_at,
                },
                "policy_report": {},
            },
        }
    )
    async def _fake_get_graph():
        return graph

    monkeypatch.setattr(worker, "get_sealai_graph_v2", _fake_get_graph)

    calls: list[str] = []

    async def _fake_apply_confirm_decision(*, graph, config, decision, edits, as_node, extra_updates=None):
        thread_id = (config.get("configurable") or {}).get("thread_id")
        calls.append(thread_id)
        assert decision == "reject"
        assert edits.get("reason") == "timeout"
        state = graph.states.get(thread_id, {})
        state["awaiting_user_confirmation"] = False
        state["confirm_status"] = "resolved"
        state["final_text"] = "Abgebrochen."
        if extra_updates:
            state.update(extra_updates)
        graph.states[thread_id] = state
        return state

    monkeypatch.setattr(worker, "apply_confirm_decision", _fake_apply_confirm_decision)

    redis = FakeRedis()
    redis.zsets[f"chat:conversations:{tenant_a}:{owner_id}"] = {chat_id: now_ts}
    redis.zsets[f"chat:conversations:{tenant_b}:{owner_id}"] = {chat_id: now_ts}

    rejected = await worker.process_hitl_timeouts_once(redis, now_ts=now_ts)

    assert rejected == 1
    assert calls == [thread_a]
    assert graph.states[thread_a]["confirm_status"] == "resolved"
    assert graph.states[thread_a]["policy_report"]["hitl_timeout"]["reason"] == "timeout"
    assert graph.states[thread_b]["confirm_status"] == "pending"
