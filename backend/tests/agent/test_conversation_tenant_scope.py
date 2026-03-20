"""
A5 Final Follow-up: tenant-scoped Conversation / History

Tests verifying that:
1. upsert_conversation writes to tenant-scoped keys when tenant_id is provided
2. upsert_conversation falls back to legacy owner-only keys when tenant_id is absent
3. _collect_for_owner reads from tenant-scoped keys (primary)
4. _collect_for_owner reads from legacy keys as fallback (pre-A5 records)
5. _collect_for_owner deduplicates: new-key entry takes priority over legacy entry
6. Same owner_id in different tenants yields separate histories
7. Cross-tenant conversation listing cannot see the other tenant's entries
8. delete_conversation removes from both tenant-scoped and legacy keys
9. list_conversations passes tenant_id through to _collect_for_owner
10. Key format contracts (sorted set and hash)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, call

import pytest

from app.services.chat.conversations import (
    ConversationMeta,
    _collect_for_owner,
    _hash_key,
    _hash_key_legacy,
    _sorted_set_key,
    _sorted_set_key_legacy,
    delete_conversation,
    list_conversations,
    upsert_conversation,
)


# ---------------------------------------------------------------------------
# Key format contracts
# ---------------------------------------------------------------------------

class TestKeyFormats:
    def test_sorted_set_key_tenant_scoped(self):
        assert _sorted_set_key("tenant-a", "user-1") == "chat:conversations:tenant-a:user-1"

    def test_sorted_set_key_legacy(self):
        assert _sorted_set_key_legacy("user-1") == "chat:conversations:user-1"

    def test_hash_key_tenant_scoped(self):
        assert _hash_key("tenant-a", "user-1", "conv-1") == "chat:conversation:tenant-a:user-1:conv-1"

    def test_hash_key_legacy(self):
        assert _hash_key_legacy("user-1", "conv-1") == "chat:conversation:user-1:conv-1"

    def test_different_tenants_different_keys(self):
        assert _sorted_set_key("tenant-a", "user-1") != _sorted_set_key("tenant-b", "user-1")
        assert _hash_key("tenant-a", "user-1", "c") != _hash_key("tenant-b", "user-1", "c")

    def test_new_key_different_from_legacy(self):
        assert _sorted_set_key("tenant-a", "user-1") != _sorted_set_key_legacy("user-1")
        assert _hash_key("tenant-a", "user-1", "c") != _hash_key_legacy("user-1", "c")


# ---------------------------------------------------------------------------
# upsert_conversation — key selection
# ---------------------------------------------------------------------------

def _make_redis_mock(existing_hash: Dict[str, Any] | None = None) -> MagicMock:
    """Return a Redis mock that records hset calls and exposes them for assertion."""
    r = MagicMock()
    r.hgetall.return_value = existing_hash or {}
    r.zcard.return_value = 0
    pipe = MagicMock()
    r.pipeline.return_value = pipe
    pipe.hset = MagicMock()
    pipe.expire = MagicMock()
    pipe.zadd = MagicMock()
    pipe.execute = MagicMock()
    return r


def _settings_mock() -> MagicMock:
    """Minimal settings stub so upsert_conversation can run without a real settings object."""
    s = MagicMock()
    s.chat_max_conversations_per_user = 0  # disables _cleanup_excess_conversations
    s.chat_history_ttl_days = 30
    return s


class TestUpsertConversationKeySelection:
    def _run_upsert(self, r: MagicMock, **kwargs) -> None:
        from unittest.mock import patch as _patch
        with _patch("app.services.chat.conversations._redis_client", return_value=r), \
             _patch("app.services.chat.conversations.settings", _settings_mock()):
            upsert_conversation(**kwargs)

    def test_with_tenant_id_writes_to_tenant_scoped_hash(self):
        r = _make_redis_mock()
        self._run_upsert(r, owner_id="user-1", conversation_id="conv-1",
                         tenant_id="tenant-a", first_user_message="hello")
        expected_hash = _hash_key("tenant-a", "user-1", "conv-1")
        r.hgetall.assert_called_once_with(expected_hash)

    def test_with_tenant_id_writes_to_tenant_scoped_sorted_set(self):
        r = _make_redis_mock()
        self._run_upsert(r, owner_id="user-1", conversation_id="conv-1",
                         tenant_id="tenant-a", first_user_message="hello")
        expected_set = _sorted_set_key("tenant-a", "user-1")
        zadd_keys = [c[0][0] for c in r.pipeline.return_value.zadd.call_args_list]
        assert expected_set in zadd_keys

    def test_without_tenant_id_writes_to_legacy_hash(self):
        r = _make_redis_mock()
        self._run_upsert(r, owner_id="user-1", conversation_id="conv-1",
                         first_user_message="hello")
        expected_hash = _hash_key_legacy("user-1", "conv-1")
        r.hgetall.assert_called_once_with(expected_hash)

    def test_without_tenant_id_writes_to_legacy_sorted_set(self):
        r = _make_redis_mock()
        self._run_upsert(r, owner_id="user-1", conversation_id="conv-1",
                         first_user_message="hello")
        expected_set = _sorted_set_key_legacy("user-1")
        zadd_keys = [c[0][0] for c in r.pipeline.return_value.zadd.call_args_list]
        assert expected_set in zadd_keys

    def test_tenant_id_stored_in_hash_mapping(self):
        r = _make_redis_mock()
        captured: Dict[str, Any] = {}

        def _hset(key, *, mapping):
            captured.update(mapping)

        r.pipeline.return_value.hset.side_effect = _hset
        self._run_upsert(r, owner_id="user-1", conversation_id="conv-1",
                         tenant_id="tenant-a", first_user_message="hello")
        assert captured.get("tenant_id") == "tenant-a"


# ---------------------------------------------------------------------------
# _collect_for_owner — tenant-scoped primary + legacy fallback
# ---------------------------------------------------------------------------

def _ts(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


def _make_hash_data(conv_id: str, updated: str, tenant_id: str | None = None) -> Dict[str, str]:
    d = {
        "id": conv_id,
        "user_id": "user-1",
        "updated_at": updated,
        "title": f"Title {conv_id}",
        "last_preview": f"Preview {conv_id}",
    }
    if tenant_id:
        d["tenant_id"] = tenant_id
    return d


class TestCollectForOwner:
    def _make_r(
        self,
        *,
        new_members: List[str] | None = None,
        new_hashes: Dict[str, Dict] | None = None,
        legacy_members: List[str] | None = None,
        legacy_hashes: Dict[str, Dict] | None = None,
        tenant_id: str = "tenant-a",
        owner_id: str = "user-1",
    ) -> MagicMock:
        new_set_key = _sorted_set_key(tenant_id, owner_id)
        legacy_set_key = _sorted_set_key_legacy(owner_id)

        def _zrevrange(key, start, end):
            if key == new_set_key:
                return new_members or []
            if key == legacy_set_key:
                return legacy_members or []
            return []

        def _hgetall(key):
            if new_hashes and key in new_hashes:
                return new_hashes[key]
            if legacy_hashes and key in legacy_hashes:
                return legacy_hashes[key]
            return {}

        r = MagicMock()
        r.zrevrange.side_effect = _zrevrange
        r.hgetall.side_effect = _hgetall
        r.zrem = MagicMock()
        return r

    def test_returns_entries_from_tenant_scoped_key(self):
        owner_id, tenant_id = "user-1", "tenant-a"
        conv_id = "conv-1"
        new_hash_key = _hash_key(tenant_id, owner_id, conv_id)
        r = self._make_r(
            new_members=[conv_id],
            new_hashes={new_hash_key: _make_hash_data(conv_id, "2024-01-01T00:00:00+00:00", tenant_id)},
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            result = _collect_for_owner(owner_id, tenant_id=tenant_id)

        assert len(result) == 1
        assert result[0].id == conv_id
        assert result[0].tenant_id == tenant_id

    def test_tenant_scoped_listing_does_not_fall_back_to_tenantless_legacy_key(self):
        owner_id, tenant_id = "user-1", "tenant-a"
        conv_id = "conv-legacy"
        legacy_hash_key = _hash_key_legacy(owner_id, conv_id)
        r = self._make_r(
            new_members=[],
            legacy_members=[conv_id],
            legacy_hashes={legacy_hash_key: _make_hash_data(conv_id, "2023-06-01T00:00:00+00:00")},
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            result = _collect_for_owner(owner_id, tenant_id=tenant_id)

        assert result == []

    def test_tenant_scoped_listing_accepts_legacy_entry_with_matching_tenant_proof(self):
        owner_id, tenant_id = "user-1", "tenant-a"
        conv_id = "conv-legacy"
        legacy_hash_key = _hash_key_legacy(owner_id, conv_id)
        r = self._make_r(
            new_members=[],
            legacy_members=[conv_id],
            legacy_hashes={legacy_hash_key: _make_hash_data(conv_id, "2023-06-01T00:00:00+00:00", tenant_id)},
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            result = _collect_for_owner(owner_id, tenant_id=tenant_id)

        assert len(result) == 1
        assert result[0].id == conv_id
        assert result[0].tenant_id == tenant_id

    def test_new_key_takes_priority_on_deduplication(self):
        """Same conv_id in both sets: new-key entry wins."""
        owner_id, tenant_id = "user-1", "tenant-a"
        conv_id = "conv-1"
        new_hash_key = _hash_key(tenant_id, owner_id, conv_id)
        legacy_hash_key = _hash_key_legacy(owner_id, conv_id)
        r = self._make_r(
            new_members=[conv_id],
            new_hashes={new_hash_key: _make_hash_data(conv_id, "2024-06-01T00:00:00+00:00", tenant_id)},
            legacy_members=[conv_id],
            legacy_hashes={legacy_hash_key: _make_hash_data(conv_id, "2023-01-01T00:00:00+00:00")},
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            result = _collect_for_owner(owner_id, tenant_id=tenant_id)

        assert len(result) == 1
        assert result[0].tenant_id == tenant_id  # new-key entry carries tenant_id

    def test_different_tenants_see_different_entries(self):
        """Same owner_id, two tenant_ids: each sees only its own conversations."""
        owner_id = "user-1"

        def _collect_for_tenant(tenant_id: str, conv_id: str) -> List[ConversationMeta]:
            new_hash_key = _hash_key(tenant_id, owner_id, conv_id)
            r = self._make_r(
                new_members=[conv_id],
                new_hashes={new_hash_key: _make_hash_data(conv_id, "2024-01-01T00:00:00+00:00", tenant_id)},
                legacy_members=[],
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
            with __import__("unittest.mock", fromlist=["patch"]).patch(
                "app.services.chat.conversations._redis_client", return_value=r
            ):
                return _collect_for_owner(owner_id, tenant_id=tenant_id)

        result_a = _collect_for_tenant("tenant-a", "conv-a")
        result_b = _collect_for_tenant("tenant-b", "conv-b")
        ids_a = {e.id for e in result_a}
        ids_b = {e.id for e in result_b}
        assert "conv-a" in ids_a
        assert "conv-b" not in ids_a
        assert "conv-b" in ids_b
        assert "conv-a" not in ids_b

    def test_without_tenant_id_reads_only_legacy_set(self):
        """When called without tenant_id (legacy path), only reads legacy sorted set."""
        owner_id = "user-1"
        conv_id = "conv-old"
        legacy_hash_key = _hash_key_legacy(owner_id, conv_id)

        r = MagicMock()
        new_set_key = _sorted_set_key("any-tenant", owner_id)
        legacy_set_key = _sorted_set_key_legacy(owner_id)

        def _zrevrange(key, start, end):
            if key == legacy_set_key:
                return [conv_id]
            return []

        r.zrevrange.side_effect = _zrevrange
        r.hgetall.side_effect = lambda k: (
            _make_hash_data(conv_id, "2023-01-01T00:00:00+00:00") if k == legacy_hash_key else {}
        )
        r.zrem = MagicMock()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            result = _collect_for_owner(owner_id)  # no tenant_id

        assert len(result) == 1
        assert result[0].id == conv_id
        # Must NOT have called zrevrange with any tenant-scoped key
        for c in r.zrevrange.call_args_list:
            assert ":any-tenant:" not in c[0][0]


# ---------------------------------------------------------------------------
# delete_conversation — cleans up both new and legacy keys
# ---------------------------------------------------------------------------

class TestDeleteConversation:
    def test_deletes_tenant_scoped_and_legacy_keys(self):
        owner_id, tenant_id, conv_id = "user-1", "tenant-a", "conv-1"
        r = MagicMock()
        pipe = MagicMock()
        r.pipeline.return_value = pipe
        r.hgetall.return_value = {"tenant_id": tenant_id}
        pipe.delete = MagicMock()
        pipe.zrem = MagicMock()
        pipe.execute = MagicMock()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            delete_conversation(owner_id, conv_id, tenant_id=tenant_id)

        deleted_keys = [c[0][0] for c in pipe.delete.call_args_list]
        zrem_keys = [c[0][0] for c in pipe.zrem.call_args_list]

        assert _hash_key(tenant_id, owner_id, conv_id) in deleted_keys
        assert _hash_key_legacy(owner_id, conv_id) in deleted_keys
        assert _sorted_set_key(tenant_id, owner_id) in zrem_keys
        assert _sorted_set_key_legacy(owner_id) in zrem_keys

    def test_tenant_scoped_delete_does_not_delete_tenantless_legacy_key(self):
        owner_id, tenant_id, conv_id = "user-1", "tenant-a", "conv-1"
        r = MagicMock()
        pipe = MagicMock()
        r.pipeline.return_value = pipe
        r.hgetall.return_value = {}
        pipe.delete = MagicMock()
        pipe.zrem = MagicMock()
        pipe.execute = MagicMock()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            delete_conversation(owner_id, conv_id, tenant_id=tenant_id)

        deleted_keys = [c[0][0] for c in pipe.delete.call_args_list]
        zrem_keys = [c[0][0] for c in pipe.zrem.call_args_list]

        assert _hash_key(tenant_id, owner_id, conv_id) in deleted_keys
        assert _hash_key_legacy(owner_id, conv_id) not in deleted_keys
        assert _sorted_set_key(tenant_id, owner_id) in zrem_keys
        assert _sorted_set_key_legacy(owner_id) not in zrem_keys

    def test_without_tenant_id_deletes_legacy_key_only(self):
        owner_id, conv_id = "user-1", "conv-1"
        r = MagicMock()
        pipe = MagicMock()
        r.pipeline.return_value = pipe
        pipe.delete = MagicMock()
        pipe.zrem = MagicMock()
        pipe.execute = MagicMock()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._redis_client", return_value=r
        ):
            delete_conversation(owner_id, conv_id)

        deleted_keys = [c[0][0] for c in pipe.delete.call_args_list]
        assert _hash_key_legacy(owner_id, conv_id) in deleted_keys
        # No tenant-scoped hash should have been deleted
        for k in deleted_keys:
            assert _hash_key("any-tenant", owner_id, conv_id) != k


# ---------------------------------------------------------------------------
# list_conversations — passes tenant_id through
# ---------------------------------------------------------------------------

class TestListConversationsTenantScope:
    def test_list_conversations_passes_tenant_id(self):
        """list_conversations forwards tenant_id to _collect_for_owner."""
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._collect_for_owner"
        ) as mock_collect:
            mock_collect.return_value = []
            list_conversations("user-1", tenant_id="tenant-a")

        mock_collect.assert_called_once_with("user-1", tenant_id="tenant-a")

    def test_list_conversations_without_tenant_id_works(self):
        """Backward compat: list_conversations without tenant_id is valid."""
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.services.chat.conversations._collect_for_owner"
        ) as mock_collect:
            mock_collect.return_value = []
            list_conversations("user-1")

        mock_collect.assert_called_once_with("user-1", tenant_id=None)
