from __future__ import annotations

import anyio
from typing import Any, Dict, Iterable

import pytest

from app.api.v1.endpoints import chat_history
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
def fake_structured_case_store(monkeypatch):
    cases: Dict[tuple[str, str], Dict[str, Any]] = {}

    async def _load_structured_case(*, owner_id: str, case_id: str):
        return cases.get((owner_id, case_id))

    async def _delete_structured_case(*, owner_id: str, case_id: str):
        cases.pop((owner_id, case_id), None)

    monkeypatch.setattr(chat_history, "load_structured_case", _load_structured_case)
    monkeypatch.setattr(chat_history, "delete_structured_case", _delete_structured_case)
    return cases


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _request_user(sub: str) -> RequestUser:
    return RequestUser(user_id=sub, username=sub, sub=sub, roles=[])


def create_conversation(
    owner_id: str,
    conversation_id: str,
    *,
    structured_cases: Dict[tuple[str, str], Dict[str, Any]] | None = None,
):
    conversations.upsert_conversation(
        owner_id=owner_id,
        conversation_id=conversation_id,
        first_user_message="Guten Tag, ich brauche Hilfe.",
        last_preview="Guten Tag, ich brauche Hilfe.",
    )
    if structured_cases is not None:
        structured_cases[(owner_id, conversation_id)] = {
            "messages": [
                {"role": "user", "content": "Erste Frage"},
                {"role": "assistant", "content": "Antwort"},
            ]
        }


def test_happy_path_conversations_and_history(
    patched_redis: FakeRedis,
    fake_structured_case_store: Dict[tuple[str, str], Dict[str, Any]],
):
    conversation_id = "conv-happy"
    create_conversation("user-a", conversation_id, structured_cases=fake_structured_case_store)

    async def _call_list():
        return await chat_history.get_conversations(current_user=_request_user("user-a"))

    async def _call_history():
        return await chat_history.get_conversation_history(conversation_id, current_user=_request_user("user-a"))

    data = anyio.run(_call_list)
    assert any(entry["thread_id"] == conversation_id for entry in data)
    assert any(entry.get("last_preview") for entry in data)

    history = anyio.run(_call_history)
    assert history["conversation_id"] == conversation_id
    assert len(history["messages"]) == 2
    assert history["messages"][0]["role"] == "user"


def test_user_isolation(
    patched_redis: FakeRedis,
    fake_structured_case_store: Dict[tuple[str, str], Dict[str, Any]],
):
    conversation_id = "conv-isolate"
    create_conversation("user-a", conversation_id, structured_cases=fake_structured_case_store)

    async def _call_list():
        return await chat_history.get_conversations(current_user=_request_user("user-b"))

    async def _call_history():
        return await chat_history.get_conversation_history(conversation_id, current_user=_request_user("user-b"))

    assert anyio.run(_call_list) == []

    with pytest.raises(chat_history.HTTPException) as excinfo:
        anyio.run(_call_history)
    assert excinfo.value.status_code == 404


def test_rename_sets_user_title_flag(patched_redis: FakeRedis):
    conversation_id = "conv-rename"
    create_conversation("user-a", conversation_id)

    new_title = "Neue Überschrift"
    async def _rename():
        return await chat_history.rename_conversation(
            conversation_id,
            chat_history.ConversationTitleUpdate(title=new_title),
            current_user=_request_user("user-a"),
        )

    async def _call_list():
        return await chat_history.get_conversations(current_user=_request_user("user-a"))

    patch_resp = anyio.run(_rename)
    assert patch_resp["title"] == new_title
    assert any(entry["title"] == new_title for entry in anyio.run(_call_list))

    hash_key = conversations._hash_key("user-a", conversation_id)
    stored = patched_redis.hgetall(hash_key)
    assert stored.get("is_title_user_defined") == "1"


def test_delete_clears_conversation(
    patched_redis: FakeRedis,
    fake_structured_case_store: Dict[tuple[str, str], Dict[str, Any]],
):
    conversation_id = "conv-delete"
    create_conversation("user-a", conversation_id, structured_cases=fake_structured_case_store)

    async def _delete():
        return await chat_history.delete_conversation_endpoint(
            conversation_id,
            current_user=_request_user("user-a"),
        )

    async def _call_list():
        return await chat_history.get_conversations(current_user=_request_user("user-a"))

    async def _call_history():
        return await chat_history.get_conversation_history(conversation_id, current_user=_request_user("user-a"))

    assert anyio.run(_delete) == {"deleted": True}
    assert anyio.run(_call_list) == []

    with pytest.raises(chat_history.HTTPException) as excinfo:
        anyio.run(_call_history)
    assert excinfo.value.status_code == 404


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
