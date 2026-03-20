import asyncio
from datetime import datetime, timezone
import os

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

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from app.api.v1.endpoints.chat_history import ConversationTitleUpdate, delete_conversation_endpoint, get_conversation_history, rename_conversation
from app.services.auth.dependencies import RequestUser
from app.services.chat.conversations import ConversationMeta


def _request_user():
    return RequestUser(user_id="canonical-user", username="tester", sub="legacy-sub", roles=[], scopes=[], tenant_id="tenant-a")


def _conversation(owner_id: str) -> ConversationMeta:
    return ConversationMeta(id="conv-1", owner_id=owner_id, tenant_id="tenant-a", title="Legacy conversation", updated_at=datetime.now(timezone.utc), last_preview="preview")


def test_legacy_owner_history_loads_structured_case_via_entry_owner(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.api.v1.endpoints.chat_history.list_conversations", lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation("legacy-sub")])

    async def _load(*, tenant_id: str, owner_id: str, case_id: str):
        captured.update({"tenant_id": tenant_id, "owner_id": owner_id, "case_id": case_id})
        return {"messages": [HumanMessage(content="hello"), AIMessage(content="world")]}

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.load_structured_case", _load)
    payload = asyncio.run(get_conversation_history("conv-1", current_user=_request_user()))
    assert captured["owner_id"] == "legacy-sub"
    assert [m["content"] for m in payload["messages"]] == ["hello", "world"]


def test_conversation_found_but_structured_case_missing_fails_closed(monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.chat_history.list_conversations", lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation("legacy-sub")])

    async def _load(*, tenant_id: str, owner_id: str, case_id: str):
        return None

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.load_structured_case", _load)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_conversation_history("conv-1", current_user=_request_user()))
    assert exc_info.value.status_code == 404


def test_legacy_owner_rename_upserts_via_entry_owner(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.api.v1.endpoints.chat_history.list_conversations", lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation("legacy-sub")])
    monkeypatch.setattr("app.api.v1.endpoints.chat_history.upsert_conversation", lambda **kwargs: captured.update(kwargs))
    payload = asyncio.run(rename_conversation("conv-1", ConversationTitleUpdate(title="Renamed"), current_user=_request_user()))
    assert captured["owner_id"] == "legacy-sub"
    assert payload["id"] == "conv-1"


def test_legacy_owner_delete_deletes_structured_case_via_entry_owner(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.api.v1.endpoints.chat_history.list_conversations", lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation("legacy-sub")])
    monkeypatch.setattr("app.api.v1.endpoints.chat_history.delete_conversation", lambda owner_id, conversation_id, tenant_id=None, reason="manual": captured.update({"metadata_owner_id": owner_id, "metadata_tenant_id": tenant_id}))

    async def _delete_structured_case(*, tenant_id: str, owner_id: str, case_id: str):
        captured.update({"structured_owner_id": owner_id, "structured_tenant_id": tenant_id})

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.delete_structured_case", _delete_structured_case)
    payload = asyncio.run(delete_conversation_endpoint("conv-1", current_user=_request_user()))
    assert payload == {"deleted": True}
    assert captured["structured_owner_id"] == "legacy-sub"
