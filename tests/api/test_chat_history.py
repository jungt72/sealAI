from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Iterable

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import chat_history, langgraph_v2
from app.core.config import settings
from app.services.chat import conversations
from app.services.auth.dependencies import RequestUser


class FakePipeline:
    def __init__(self, redis: "FakeRedis"):
        self.redis = redis
        self.ops: list = []

    def hset(self, key: str, mapping: Dict[str, Any] | None = None):
        if mapping:
            self.ops.append(lambda: self.redis.hset(key, mapping))
        return self

    def expire(self, key: str, seconds: int):
        return self

    def zadd(self, key: str, mapping: Dict[str, float]):
        self.ops.append(lambda: self.redis.zadd(key, mapping))
        return self

    def zrem(self, key: str, member: str):
        self.ops.append(lambda: self.redis.zrem(key, member))
        return self

    def delete(self, key: str):
        self.ops.append(lambda: self.redis.delete(key))
        return self

    def execute(self):
        for op in self.ops:
            op()


class FakeRedis:
    def __init__(self):
        self.hashes: Dict[str, Dict[str, str]] = {}
        self.sorted_sets: Dict[str, Dict[str, float]] = {}

    def pipeline(self):
        return FakePipeline(self)

    def hset(self, key: str, mapping: Dict[str, Any]):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})

    def hgetall(self, key: str) -> Dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def expire(self, key: str, seconds: int):
        return True

    def zadd(self, key: str, mapping: Dict[str, float]):
        self.sorted_sets.setdefault(key, {})
        for member, score in mapping.items():
            self.sorted_sets[key][member] = float(score)

    def zrange(self, key: str, start: int, stop: int) -> list[str]:
        items = sorted(self.sorted_sets.get(key, {}).items(), key=lambda pair: (pair[1], pair[0]))
        return self._slice_members(items, start, stop)

    def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        items = sorted(self.sorted_sets.get(key, {}).items(), key=lambda pair: (-pair[1], pair[0]))
        return self._slice_members(items, start, stop)

    def zcard(self, key: str) -> int:
        return len(self.sorted_sets.get(key, {}))

    def zrem(self, key: str, member: str):
        self.sorted_sets.get(key, {}).pop(member, None)

    def delete(self, key: str):
        self.hashes.pop(key, None)

    @staticmethod
    def _slice_members(items: Iterable[tuple[str, float]], start: int, stop: int) -> list[str]:
        member_list = [member for member, _ in items]
        if stop == -1:
            sliced = member_list[start:]
        else:
            sliced = member_list[start : stop + 1]
        return sliced


@pytest.fixture(autouse=True)
def fake_verify(monkeypatch):
    import app.services.auth.token as auth_token

    def _fake_verify(token: str):
        sub = token
        return {"sub": sub, "preferred_username": sub}

    monkeypatch.setattr(auth_token, "verify_access_token", _fake_verify)


@pytest.fixture
def patched_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(conversations, "_redis_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def fake_graph(monkeypatch):
    class FakeSnapshot:
        def __init__(self):
            self.values = {
                "messages": [
                    {"role": "user", "content": "Erste Frage"},
                    {"role": "assistant", "content": "Antwort"},
                ]
            }
            self.next = None
            self.config = {}

    class FakeCheckpointer:
        async def adelete_thread(self, thread_id: str):
            return

    class FakeGraph:
        def __init__(self):
            self.checkpointer = FakeCheckpointer()

        async def aget_state(self, config):
            return FakeSnapshot()

    async def _build(thread_id: str, user_id: str):
        return FakeGraph(), {"thread_id": thread_id, "user_id": user_id}

    monkeypatch.setattr(chat_history, "_build_state_config_with_checkpointer", _build)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(app, patched_redis):
    return TestClient(app)


def auth_headers(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sub}"}


def create_conversation(owner_id: str, conversation_id: str):
    conversations.upsert_conversation(
        owner_id=owner_id,
        conversation_id=conversation_id,
        first_user_message="Guten Tag, ich brauche Hilfe.",
        last_preview="Guten Tag, ich brauche Hilfe.",
    )


def test_happy_path_conversations_and_history(client: TestClient, patched_redis: FakeRedis):
    conversation_id = "conv-happy"
    create_conversation("user-a", conversation_id)

    list_resp = client.get("/api/v1/chat/conversations", headers=auth_headers("user-a"))
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert any(entry["thread_id"] == conversation_id for entry in data)
    assert any(entry.get("last_preview") for entry in data)

    history_resp = client.get(f"/api/v1/chat/history/{conversation_id}", headers=auth_headers("user-a"))
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert history["conversation_id"] == conversation_id
    assert len(history["messages"]) == 2
    assert history["messages"][0]["role"] == "user"


def test_user_isolation(client: TestClient, patched_redis: FakeRedis):
    conversation_id = "conv-isolate"
    create_conversation("user-a", conversation_id)

    resp = client.get("/api/v1/chat/conversations", headers=auth_headers("user-b"))
    assert resp.status_code == 200
    assert resp.json() == []

    history_resp = client.get(f"/api/v1/chat/history/{conversation_id}", headers=auth_headers("user-b"))
    assert history_resp.status_code == 404


def test_rename_sets_user_title_flag(client: TestClient, patched_redis: FakeRedis):
    conversation_id = "conv-rename"
    create_conversation("user-a", conversation_id)

    new_title = "Neue Überschrift"
    patch_resp = client.patch(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_headers("user-a"),
        json={"title": new_title},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == new_title

    list_resp = client.get("/api/v1/chat/conversations", headers=auth_headers("user-a"))
    assert any(entry["title"] == new_title for entry in list_resp.json())

    canonical_key = conversations._canonical_owner_key("user-a")
    hash_key = conversations._hash_key(canonical_key, conversation_id)
    stored = patched_redis.hgetall(hash_key)
    assert stored.get("is_title_user_defined") == "1"


def test_delete_clears_conversation(client: TestClient, patched_redis: FakeRedis):
    conversation_id = "conv-delete"
    create_conversation("user-a", conversation_id)

    del_resp = client.delete(f"/api/v1/chat/conversations/{conversation_id}", headers=auth_headers("user-a"))
    assert del_resp.status_code == 200

    list_resp = client.get("/api/v1/chat/conversations", headers=auth_headers("user-a"))
    assert list_resp.json() == []

    history_resp = client.get(f"/api/v1/chat/history/{conversation_id}", headers=auth_headers("user-a"))
    assert history_resp.status_code == 404


def test_limit_removes_oldest_conversation(monkeypatch, patched_redis: FakeRedis):
    monkeypatch.setattr(settings, "chat_max_conversations_per_user", 1)
    create_conversation("user-a", "conv-old")
    create_conversation("user-a", "conv-new")

    entries = conversations.list_conversations("user-a")
    assert len(entries) == 1
    assert entries[0].id == "conv-new"


def test_list_merges_legacy_owner(patched_redis: FakeRedis):
    conversations.upsert_conversation(
        owner_id="legacy-user",
        conversation_id="conv-legacy",
        first_user_message="Legacy chat",
        last_preview="Legacy chat last preview",
    )

    entries = conversations.list_conversations("current-user", legacy_owner_id="legacy-user")
    assert len(entries) == 1
    assert entries[0].id == "conv-legacy"


@pytest.mark.anyio(backend="asyncio")
async def test_langgraph_chat_v2_upserts_metadata(monkeypatch):
    recorded: dict[str, Any] = {}

    class FakeBroadcast:
        async def record_event(self, **_kwargs: Any) -> int:
            return 1

        async def subscribe(self, **_kwargs: Any):
            return None

        async def replay_after(self, **_kwargs: Any) -> tuple[list[Any], bool]:
            return [], True

        async def unsubscribe(self, **_kwargs: Any) -> None:
            return None

        async def broadcast(self, **_kwargs: Any) -> None:
            return None

        def parse_last_event_id(self, *args: Any, **_kwargs: Any) -> Any:
            return None

    monkeypatch.setattr(langgraph_v2, "sse_broadcast", FakeBroadcast())

    async def fake_stream(req, *, user_id, request_id, last_event_id, tenant_id=None, legacy_user_id=None):
        if False:
            yield b""

    monkeypatch.setattr(langgraph_v2, "_event_stream_v2", fake_stream)

    def fake_upsert(owner_ids=None, owner_id: str | None = None, conversation_id: str | None = None, **kwargs: Any):
        resolved_owner_id = owner_ids.canonical if owner_ids else owner_id
        recorded["owner_id"] = resolved_owner_id
        recorded["conversation_id"] = conversation_id
        recorded["kwargs"] = kwargs

    monkeypatch.setattr(conversations, "upsert_conversation", fake_upsert)
    monkeypatch.setattr(langgraph_v2, "upsert_conversation", fake_upsert)

    request_model = langgraph_v2.LangGraphV2Request(input="Test preview", chat_id="thread-preview")
    raw_request = SimpleNamespace(headers={"X-Request-Id": "req-1"})
    user = RequestUser(user_id="user-preview", username="user-preview", sub="user-preview", roles=[])
    await langgraph_v2.langgraph_chat_v2_endpoint(request_model, raw_request, user)

    assert recorded.get("owner_id") == "user-preview"
    assert recorded.get("conversation_id") == "thread-preview"
    assert recorded.get("kwargs", {}).get("last_preview") == "Test preview"
