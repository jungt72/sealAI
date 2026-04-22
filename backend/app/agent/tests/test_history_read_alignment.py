from __future__ import annotations

import types
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from app.agent.api.routes import history as history_routes
from app.agent.state.models import ConversationMessage, GovernedSessionState
from app.services.auth.dependencies import RequestUser


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="ignored-sub",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


def _governed_state(content: str) -> GovernedSessionState:
    return GovernedSessionState(
        conversation_messages=[
            ConversationMessage(role="user", content=content),
        ]
    )


@pytest.mark.asyncio
async def test_chat_history_prefers_live_governed_history(monkeypatch: pytest.MonkeyPatch) -> None:
    live_state = _governed_state("Live governed")
    load_live = AsyncMock(return_value=live_state)
    load_snapshot = AsyncMock(side_effect=AssertionError("snapshot should not be read when live governed exists"))
    load_structured = AsyncMock(side_effect=AssertionError("structured fallback should not be read when governed exists"))

    monkeypatch.setattr("app.agent.api.loaders._load_live_governed_state", load_live)
    monkeypatch.setattr(history_routes, "get_latest_governed_case_snapshot_async", load_snapshot)
    monkeypatch.setattr(history_routes, "load_structured_case", load_structured)

    payload = await history_routes.get_live_chat_history("case-1", current_user=_user())

    assert [(item.role, item.content) for item in payload] == [("user", "Live governed")]
    load_live.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_history_uses_latest_snapshot_before_structured_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    snapshot_state = _governed_state("Snapshot governed")

    async def _load_snapshot(*, case_number: str, user_id: str | None = None):
        captured["case_number"] = case_number
        captured["user_id"] = user_id
        return types.SimpleNamespace(state_json=snapshot_state.model_dump(mode="json"))

    monkeypatch.setattr("app.agent.api.loaders._load_live_governed_state", AsyncMock(return_value=None))
    monkeypatch.setattr(history_routes, "get_latest_governed_case_snapshot_async", _load_snapshot)
    monkeypatch.setattr(
        history_routes,
        "load_structured_case",
        AsyncMock(side_effect=AssertionError("structured fallback should not be read when snapshot exists")),
    )

    payload = await history_routes.get_live_chat_history("case-2", current_user=_user())

    assert [(item.role, item.content) for item in payload] == [("user", "Snapshot governed")]
    assert captured == {"case_number": "case-2", "user_id": "user-1"}


@pytest.mark.asyncio
async def test_chat_history_uses_structured_fallback_when_governed_sources_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _load_structured(*, tenant_id: str, owner_id: str, case_id: str):
        captured["tenant_id"] = tenant_id
        captured["owner_id"] = owner_id
        captured["case_id"] = case_id
        return {"messages": [HumanMessage(content="Structured legacy")]}

    monkeypatch.setattr("app.agent.api.loaders._load_live_governed_state", AsyncMock(return_value=None))
    monkeypatch.setattr(history_routes, "get_latest_governed_case_snapshot_async", AsyncMock(return_value=None))
    monkeypatch.setattr(history_routes, "load_structured_case", _load_structured)

    payload = await history_routes.get_live_chat_history("case-3", current_user=_user())

    assert [(item.role, item.content) for item in payload] == [("user", "Structured legacy")]
    assert captured == {
        "tenant_id": "tenant-1",
        "owner_id": "user-1",
        "case_id": "case-3",
    }


@pytest.mark.asyncio
async def test_chat_history_returns_empty_when_all_sources_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.agent.api.loaders._load_live_governed_state", AsyncMock(return_value=None))
    monkeypatch.setattr(history_routes, "get_latest_governed_case_snapshot_async", AsyncMock(return_value=None))
    monkeypatch.setattr(history_routes, "load_structured_case", AsyncMock(return_value=None))

    payload = await history_routes.get_live_chat_history("case-4", current_user=_user())

    assert payload == []
