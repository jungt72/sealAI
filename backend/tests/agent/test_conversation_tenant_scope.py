from datetime import datetime, timezone
import os
from unittest.mock import MagicMock, patch

for key, value in {
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "test",
    "database_url": "sqlite+aiosqlite:///tmp.db",
    "POSTGRES_SYNC_URL": "sqlite:///tmp.db",
    "openai_api_key": "test",
    "qdrant_url": "http://localhost",
    "redis_url": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost",
    "nextauth_secret": "secret",
    "keycloak_issuer": "http://localhost",
    "keycloak_jwks_url": "http://localhost/jwks",
    "keycloak_client_id": "client",
    "keycloak_client_secret": "secret",
    "keycloak_expected_azp": "client",
}.items():
    os.environ.setdefault(key, value)

from app.services.chat.conversations import (
    _collect_for_owner,
    _hash_key,
    _hash_key_legacy,
    _sorted_set_key,
    _sorted_set_key_legacy,
    delete_conversation,
    upsert_conversation,
)


def _settings_mock():
    s = MagicMock()
    s.chat_max_conversations_per_user = 0
    s.chat_history_ttl_days = 30
    return s


def test_key_formats():
    assert _sorted_set_key("tenant-a", "user-1") == "chat:conversations:tenant-a:user-1"
    assert _sorted_set_key_legacy("user-1") == "chat:conversations:user-1"
    assert _hash_key("tenant-a", "user-1", "conv-1") == "chat:conversation:tenant-a:user-1:conv-1"
    assert _hash_key_legacy("user-1", "conv-1") == "chat:conversation:user-1:conv-1"


def test_upsert_uses_tenant_scoped_keys_when_tenant_present():
    r = MagicMock()
    r.hgetall.return_value = {}
    r.zcard.return_value = 0
    r.pipeline.return_value = MagicMock()
    with patch("app.services.chat.conversations._redis_client", return_value=r), patch("app.services.chat.conversations.settings", _settings_mock()):
        upsert_conversation(owner_id="user-1", conversation_id="conv-1", tenant_id="tenant-a", first_user_message="hello")
    r.hgetall.assert_called_once_with("chat:conversation:tenant-a:user-1:conv-1")


def test_collect_for_owner_rejects_tenantless_legacy_entry_for_tenant_scoped_listing():
    r = MagicMock()
    r.zrevrange.side_effect = lambda key, start, end: [] if key == _sorted_set_key("tenant-a", "user-1") else ["conv-legacy"]
    r.hgetall.return_value = {"id": "conv-legacy", "user_id": "user-1", "updated_at": datetime.now(timezone.utc).isoformat(), "title": "Legacy", "last_preview": "preview"}
    with patch("app.services.chat.conversations._redis_client", return_value=r):
        assert _collect_for_owner("user-1", tenant_id="tenant-a") == []


def test_delete_conversation_removes_tenant_scoped_and_matching_legacy_keys():
    r = MagicMock()
    r.pipeline.return_value = MagicMock()
    r.hgetall.return_value = {"tenant_id": "tenant-a"}
    with patch("app.services.chat.conversations._redis_client", return_value=r):
        delete_conversation("user-1", "conv-1", tenant_id="tenant-a")
    calls = [call.args[0] for call in r.pipeline.return_value.delete.call_args_list]
    assert "chat:conversation:tenant-a:user-1:conv-1" in calls
    assert "chat:conversation:user-1:conv-1" in calls
