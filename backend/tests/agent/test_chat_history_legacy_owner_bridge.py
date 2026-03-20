from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from app.api.v1.endpoints.chat_history import (
    ConversationTitleUpdate,
    delete_conversation_endpoint,
    get_conversation_history,
    rename_conversation,
)
from app.services.auth.dependencies import RequestUser
from app.services.chat.conversations import ConversationMeta


@pytest.fixture()
def request_user() -> RequestUser:
    return RequestUser(
        user_id="canonical-user",
        username="tester",
        sub="legacy-sub",
        roles=[],
        scopes=[],
        tenant_id="tenant-a",
    )


def _conversation(*, owner_id: str, conversation_id: str = "conv-1") -> ConversationMeta:
    return ConversationMeta(
        id=conversation_id,
        owner_id=owner_id,
        tenant_id="tenant-a",
        title="Legacy conversation",
        updated_at=datetime.now(timezone.utc),
        last_preview="preview",
    )


def test_legacy_owner_history_loads_structured_case_via_entry_owner(monkeypatch, request_user):
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_history.list_conversations",
        lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation(owner_id="legacy-sub")],
    )

    async def _load(*, tenant_id: str, owner_id: str, case_id: str):
        captured["tenant_id"] = tenant_id
        captured["owner_id"] = owner_id
        captured["case_id"] = case_id
        return {
            "messages": [
                HumanMessage(content="hello"),
                AIMessage(content="world"),
            ],
        }

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.load_structured_case", _load)

    payload = asyncio.run(get_conversation_history("conv-1", current_user=request_user))

    assert captured == {
        "tenant_id": "tenant-a",
        "owner_id": "legacy-sub",
        "case_id": "conv-1",
    }
    assert [message["content"] for message in payload["messages"]] == ["hello", "world"]


def test_legacy_owner_delete_deletes_structured_case_via_entry_owner(monkeypatch, request_user):
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_history.list_conversations",
        lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation(owner_id="legacy-sub")],
    )

    def _delete_conversation(owner_id: str, conversation_id: str, *, tenant_id: str | None = None, reason: str = "manual"):
        captured["metadata_owner_id"] = owner_id
        captured["metadata_tenant_id"] = str(tenant_id)
        captured["metadata_case_id"] = conversation_id

    async def _delete_structured_case(*, tenant_id: str, owner_id: str, case_id: str):
        captured["structured_owner_id"] = owner_id
        captured["structured_tenant_id"] = tenant_id
        captured["structured_case_id"] = case_id

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.delete_conversation", _delete_conversation)
    monkeypatch.setattr("app.api.v1.endpoints.chat_history.delete_structured_case", _delete_structured_case)

    payload = asyncio.run(delete_conversation_endpoint("conv-1", current_user=request_user))

    assert payload == {"deleted": True}
    assert captured["metadata_owner_id"] == "legacy-sub"
    assert captured["structured_owner_id"] == "legacy-sub"
    assert captured["metadata_tenant_id"] == "tenant-a"
    assert captured["structured_tenant_id"] == "tenant-a"


def test_conversation_found_but_structured_case_missing_fails_closed(monkeypatch, request_user):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_history.list_conversations",
        lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation(owner_id="legacy-sub")],
    )

    async def _load(*, tenant_id: str, owner_id: str, case_id: str):
        return None

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.load_structured_case", _load)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_conversation_history("conv-1", current_user=request_user))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Structured case not found for conversation"


def test_same_owner_history_behavior_unchanged(monkeypatch):
    current_user = RequestUser(
        user_id="same-owner",
        username="tester",
        sub="same-owner",
        roles=[],
        scopes=[],
        tenant_id="tenant-a",
    )
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_history.list_conversations",
        lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation(owner_id="same-owner")],
    )

    async def _load(*, tenant_id: str, owner_id: str, case_id: str):
        captured["tenant_id"] = tenant_id
        captured["owner_id"] = owner_id
        captured["case_id"] = case_id
        return {"messages": [AIMessage(content="ok")]}

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.load_structured_case", _load)

    payload = asyncio.run(get_conversation_history("conv-1", current_user=current_user))

    assert captured == {
        "tenant_id": "tenant-a",
        "owner_id": "same-owner",
        "case_id": "conv-1",
    }
    assert len(payload["messages"]) == 1


def test_legacy_owner_rename_upserts_via_entry_owner(monkeypatch, request_user):
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_history.list_conversations",
        lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation(owner_id="legacy-sub")],
    )

    def _upsert(
        *,
        owner_id: str,
        conversation_id: str,
        tenant_id: str | None = None,
        title: str | None = None,
        updated_at=None,
        **_: object,
    ):
        captured["owner_id"] = owner_id
        captured["conversation_id"] = conversation_id
        captured["tenant_id"] = str(tenant_id)
        captured["title"] = str(title)

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.upsert_conversation", _upsert)

    payload = asyncio.run(
        rename_conversation(
            "conv-1",
            ConversationTitleUpdate(title="Renamed"),
            current_user=request_user,
        )
    )

    assert captured == {
        "owner_id": "legacy-sub",
        "conversation_id": "conv-1",
        "tenant_id": "tenant-a",
        "title": "Renamed",
    }
    assert payload["id"] == "conv-1"
    assert payload["title"] == "Legacy conversation"


def test_same_owner_rename_behavior_unchanged(monkeypatch):
    current_user = RequestUser(
        user_id="same-owner",
        username="tester",
        sub="same-owner",
        roles=[],
        scopes=[],
        tenant_id="tenant-a",
    )
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_history.list_conversations",
        lambda owner_id, legacy_owner_id=None, tenant_id=None: [_conversation(owner_id="same-owner")],
    )

    def _upsert(
        *,
        owner_id: str,
        conversation_id: str,
        tenant_id: str | None = None,
        title: str | None = None,
        updated_at=None,
        **_: object,
    ):
        captured["owner_id"] = owner_id
        captured["conversation_id"] = conversation_id
        captured["tenant_id"] = str(tenant_id)
        captured["title"] = str(title)

    monkeypatch.setattr("app.api.v1.endpoints.chat_history.upsert_conversation", _upsert)

    payload = asyncio.run(
        rename_conversation(
            "conv-1",
            ConversationTitleUpdate(title="Renamed"),
            current_user=current_user,
        )
    )

    assert captured == {
        "owner_id": "same-owner",
        "conversation_id": "conv-1",
        "tenant_id": "tenant-a",
        "title": "Renamed",
    }
    assert payload["id"] == "conv-1"
    assert payload["title"] == "Legacy conversation"
