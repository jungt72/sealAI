from __future__ import annotations

from datetime import datetime, timezone

from app.services.chat import conversations


class FakePipeline:
    def __init__(self, client: "FakeRedis") -> None:
        self._client = client
        self._commands: list[tuple[str, tuple, dict]] = []

    def hset(self, key: str, mapping: dict) -> "FakePipeline":
        self._commands.append(("hset", (key, mapping), {}))
        return self

    def expire(self, key: str, ttl: int) -> "FakePipeline":
        self._commands.append(("expire", (key, ttl), {}))
        return self

    def zadd(self, key: str, mapping: dict) -> "FakePipeline":
        self._commands.append(("zadd", (key, mapping), {}))
        return self

    def delete(self, key: str) -> "FakePipeline":
        self._commands.append(("delete", (key,), {}))
        return self

    def zrem(self, key: str, member: str) -> "FakePipeline":
        self._commands.append(("zrem", (key, member), {}))
        return self

    def execute(self) -> None:
        for name, args, kwargs in self._commands:
            getattr(self._client, name)(*args, **kwargs)
        self._commands.clear()


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    def hgetall(self, key: str) -> dict:
        return dict(self.hashes.get(key, {}))

    def hset(self, key: str, mapping: dict) -> None:
        data = self.hashes.setdefault(key, {})
        data.update(mapping)

    def delete(self, key: str) -> None:
        self.hashes.pop(key, None)

    def expire(self, key: str, ttl: int) -> None:
        return None

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        data = self.sorted_sets.setdefault(key, {})
        data.update(mapping)

    def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        data = self.sorted_sets.get(key, {})
        ordered = sorted(data.items(), key=lambda item: (-item[1], item[0]))
        members = [member for member, _score in ordered]
        if end == -1:
            return members[start:]
        return members[start : end + 1]

    def zrem(self, key: str, *members: str) -> None:
        data = self.sorted_sets.get(key)
        if not data:
            return
        for member in members:
            data.pop(member, None)

    def zcard(self, key: str) -> int:
        return len(self.sorted_sets.get(key, {}))

    def zremrangebyrank(self, key: str, start: int, end: int) -> None:
        data = self.sorted_sets.get(key, {})
        ordered = sorted(data.items(), key=lambda item: (item[1], item[0]))
        members = [member for member, _score in ordered]
        if end == -1:
            target = members[start:]
        else:
            target = members[start : end + 1]
        for member in target:
            data.pop(member, None)


def _seed_conversation(
    fake: FakeRedis,
    *,
    owner_id: str,
    owner_key: str,
    conversation_id: str,
    updated_at: datetime,
    title: str,
) -> None:
    set_key = conversations._sorted_set_key(owner_key)
    hash_key = conversations._hash_key(owner_key, conversation_id)
    fake.zadd(set_key, {conversation_id: updated_at.timestamp()})
    fake.hset(
        hash_key,
        mapping={
            "id": conversation_id,
            "user_id": owner_id,
            "updated_at": updated_at.isoformat(),
            "title": title,
            conversations._PREVIEW_FIELD: "",
        },
    )


def _configure_fake_redis(monkeypatch) -> FakeRedis:
    class DummySettings:
        chat_max_conversations_per_user = 500
        chat_history_ttl_days = 30

    fake = FakeRedis()
    monkeypatch.setattr(conversations, "_settings", lambda: DummySettings())
    monkeypatch.setattr(conversations, "_redis_client", lambda: fake)
    return fake


def test_list_uses_canonical_when_present(monkeypatch) -> None:
    fake = _configure_fake_redis(monkeypatch)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    canonical_id = "user-c"
    owner_key = conversations._canonical_owner_key(canonical_id)
    _seed_conversation(
        fake,
        owner_id=canonical_id,
        owner_key=owner_key,
        conversation_id="conv-1",
        updated_at=now,
        title="Canonical",
    )

    owner_ids = conversations.OwnerIds(canonical=canonical_id, legacy="user-l")
    results = conversations.list_conversations(owner_ids)

    assert [entry.id for entry in results] == ["conv-1"]
    assert results[0].title == "Canonical"
    assert results[0].owner_id == canonical_id


def test_list_falls_back_to_legacy(monkeypatch) -> None:
    fake = _configure_fake_redis(monkeypatch)
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)
    legacy_id = "user-l"
    _seed_conversation(
        fake,
        owner_id=legacy_id,
        owner_key=legacy_id,
        conversation_id="conv-legacy",
        updated_at=now,
        title="Legacy",
    )

    owner_ids = conversations.OwnerIds(canonical="user-c", legacy=legacy_id)
    results = conversations.list_conversations(owner_ids)

    assert [entry.id for entry in results] == ["conv-legacy"]
    assert results[0].title == "Legacy"
    assert results[0].owner_id == legacy_id


def test_list_merges_and_prefers_canonical(monkeypatch) -> None:
    fake = _configure_fake_redis(monkeypatch)
    canonical_id = "user-c"
    legacy_id = "user-l"
    canonical_key = conversations._canonical_owner_key(canonical_id)
    _seed_conversation(
        fake,
        owner_id=canonical_id,
        owner_key=canonical_key,
        conversation_id="conv-1",
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        title="Canonical",
    )
    _seed_conversation(
        fake,
        owner_id=legacy_id,
        owner_key=legacy_id,
        conversation_id="conv-1",
        updated_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        title="Legacy",
    )
    _seed_conversation(
        fake,
        owner_id=legacy_id,
        owner_key=legacy_id,
        conversation_id="conv-2",
        updated_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        title="Legacy Unique",
    )

    owner_ids = conversations.OwnerIds(canonical=canonical_id, legacy=legacy_id)
    results = conversations.list_conversations(owner_ids)

    ids = [entry.id for entry in results]
    assert ids == ["conv-2", "conv-1"]
    canonical_entry = next(entry for entry in results if entry.id == "conv-1")
    assert canonical_entry.title == "Canonical"
    assert canonical_entry.owner_id == canonical_id


def test_upsert_writes_canonical_and_legacy(monkeypatch) -> None:
    fake = _configure_fake_redis(monkeypatch)
    owner_ids = conversations.OwnerIds(canonical="user-c", legacy="user-l")
    updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    conversations.upsert_conversation(
        owner_ids=owner_ids,
        conversation_id="conv-1",
        title="Title",
        updated_at=updated_at,
    )

    canonical_key = conversations._canonical_owner_key("user-c")
    canonical_hash = conversations._hash_key(canonical_key, "conv-1")
    legacy_hash = conversations._hash_key("user-l", "conv-1")
    assert canonical_hash in fake.hashes
    assert legacy_hash in fake.hashes


def test_delete_removes_canonical_and_legacy(monkeypatch) -> None:
    fake = _configure_fake_redis(monkeypatch)
    owner_ids = conversations.OwnerIds(canonical="user-c", legacy="user-l")
    updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    conversations.upsert_conversation(
        owner_ids=owner_ids,
        conversation_id="conv-1",
        title="Title",
        updated_at=updated_at,
    )
    conversations.delete_conversation(owner_ids, "conv-1")

    canonical_key = conversations._canonical_owner_key("user-c")
    canonical_hash = conversations._hash_key(canonical_key, "conv-1")
    legacy_hash = conversations._hash_key("user-l", "conv-1")
    assert canonical_hash not in fake.hashes
    assert legacy_hash not in fake.hashes
