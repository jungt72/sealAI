from __future__ import annotations

import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.api import streaming
from app.agent.api.governed_runtime import (
    GovernedGraphTurnResult,
    build_governed_graph_input,
)
from app.agent.api.routes import chat
from app.agent.graph import GraphState
from app.agent.state.models import ConversationMessage, GovernedSessionState
from app.services.auth.dependencies import RequestUser


def _request_user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="user-1",
        sub="user-1",
        roles=["user"],
        scopes=[],
        tenant_id="tenant-1",
    )


def test_build_governed_graph_input_maps_live_session_state_once() -> None:
    governed = GovernedSessionState(
        conversation_messages=[ConversationMessage(role="user", content="Vorher")]
    )

    graph_input = build_governed_graph_input(
        governed_state=governed,
        message="Bitte PTFE-RWDR prüfen",
        current_user=_request_user(),
        session_id="case-1",
    )

    assert graph_input.tenant_id == "tenant-1"
    assert graph_input.session_id == "case-1"
    assert graph_input.pending_message == "Bitte PTFE-RWDR prüfen"
    assert [message.content for message in graph_input.conversation_messages] == [
        "Vorher",
        "Bitte PTFE-RWDR prüfen",
    ]
    assert graph_input.asserted == governed.asserted
    assert graph_input.governance == governed.governance
    assert graph_input.normalized == governed.normalized


def test_governed_graph_input_mapping_is_not_redeclared_in_json_or_sse_callers() -> None:
    assert "GraphState(" not in inspect.getsource(chat)
    assert "GraphState(" not in inspect.getsource(streaming)


@pytest.mark.asyncio
async def test_json_governed_path_uses_governed_runtime_seam() -> None:
    result_state = GraphState(output_reply="Bitte Medium angeben.")
    persisted_state = GovernedSessionState()
    seam = AsyncMock(
        return_value=GovernedGraphTurnResult(
            result_state=result_state,
            persisted_state=persisted_state,
            progress_events=[],
        )
    )

    request = SimpleNamespace(session_id="case-json", message="Ich brauche eine Dichtung")
    with patch("app.agent.api.routes.chat.run_governed_graph_turn", seam):
        returned_result, returned_persisted = await chat._run_governed_graph_once(
            request,
            current_user=_request_user(),
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    seam.assert_awaited_once_with(
        request=request,
        current_user=_request_user(),
        pre_gate_classification="DOMAIN_INQUIRY",
    )
    assert returned_result is result_state
    assert returned_persisted is persisted_state


@pytest.mark.asyncio
async def test_sse_governed_path_uses_governed_runtime_seam_and_keeps_contract() -> None:
    result_state = GraphState(
        output_reply="Bitte Medium angeben.",
        output_response_class="structured_clarification",
    )
    persisted_state = GovernedSessionState()
    seam = AsyncMock(
        return_value=GovernedGraphTurnResult(
            result_state=result_state,
            persisted_state=persisted_state,
            progress_events=[{"event_type": "evidence_retrieved"}],
        )
    )

    request = SimpleNamespace(session_id="case-sse", message="Ich brauche eine Dichtung")
    with (
        patch("app.agent.api.streaming.run_governed_graph_turn", seam),
        patch(
            "app.agent.api.streaming.collect_governed_visible_reply",
            AsyncMock(return_value="Welches Medium soll abgedichtet werden?"),
        ),
    ):
        frames = [
            frame
            async for frame in streaming._stream_governed_graph(
                request,
                current_user=_request_user(),
                pre_gate_classification="DOMAIN_INQUIRY",
            )
        ]

    seam.assert_awaited_once_with(
        request=request,
        current_user=_request_user(),
        pre_gate_classification="DOMAIN_INQUIRY",
        collect_progress=True,
    )
    payloads = [
        json.loads(frame[6:].strip())
        for frame in frames
        if frame.startswith("data: ") and not frame.startswith("data: [DONE]")
    ]
    assert payloads[0] == {
        "type": "progress",
        "data": {"event_type": "evidence_retrieved"},
    }
    assert payloads[1]["type"] == "state_update"
    assert payloads[1]["reply"] == "Welches Medium soll abgedichtet werden?"
    assert payloads[1]["response_class"] == "structured_clarification"
    assert frames[-1] == "data: [DONE]\n\n"
