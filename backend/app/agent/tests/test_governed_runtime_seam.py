from __future__ import annotations

import inspect
import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

from app.agent.api import streaming
from app.agent.api.governed_runtime import (
    GovernedGraphTurnResult,
    build_governed_graph_input,
    run_governed_graph_turn,
)
from app.agent.api.loaders import _update_governed_state_post_graph
from app.agent.api.routes import chat
from app.agent.graph import GraphState
from app.agent.state.models import ChallengeState, ConversationMessage, GovernedSessionState
from app.agent.v92.models import (
    CalculationState,
    DossierState,
    EngineeringState,
    SealSystemState,
)
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


def test_visible_stream_segments_split_large_model_delta_without_text_changes() -> None:
    text = (
        "Bei mineralöl- oder hydrauliköl-nahen Medien ist EPDM eher ein Warnpunkt, "
        "während NBR und FKM Prüfhypothesen bleiben."
    )

    segments = streaming._visible_stream_segments(text)

    assert len(segments) > 1
    assert "".join(segments) == text
    assert all(len(segment) <= 48 for segment in segments)


def test_build_governed_graph_input_maps_live_session_state_once() -> None:
    governed = GovernedSessionState(
        conversation_messages=[ConversationMessage(role="user", content="Vorher")]
    )

    graph_input = build_governed_graph_input(
        governed_state=governed,
        message="Bitte PTFE-RWDR prüfen",
        current_user=_request_user(),
        session_id="case-1",
        defer_visible_answer_composer=True,
    )

    assert graph_input.tenant_id == "tenant-1"
    assert graph_input.session_id == "case-1"
    assert graph_input.pending_message == "Bitte PTFE-RWDR prüfen"
    assert graph_input.defer_visible_answer_composer is True
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
async def test_governed_runtime_uses_async_graph_provider_for_streaming() -> None:
    class FakeAsyncGraph:
        graph_input: GraphState | None = None
        config: dict[str, object] | None = None
        stream_mode: list[str] | None = None

        async def astream(self, graph_input, *, config, stream_mode):  # noqa: ANN001
            self.graph_input = graph_input
            self.config = config
            self.stream_mode = stream_mode
            yield (
                "values",
                GraphState(
                    output_reply="Gern. Wenn du weiter machen möchtest, bin ich da.",
                    output_response_class="conversational_answer",
                ),
            )

    fake_graph = FakeAsyncGraph()
    request = SimpleNamespace(session_id="case-stream", message="danke")
    persisted_state = GovernedSessionState()

    with (
        patch(
            "app.agent.api.governed_runtime._load_live_governed_state",
            AsyncMock(return_value=GovernedSessionState()),
        ),
        patch(
            "app.agent.api.governed_runtime.get_governed_graph",
            AsyncMock(return_value=fake_graph),
        ) as graph_provider,
        patch(
            "app.agent.api.governed_runtime._update_governed_state_post_graph",
            AsyncMock(return_value=persisted_state),
        ),
        patch("app.agent.api.governed_runtime.emit_quality_trace"),
    ):
        result = await run_governed_graph_turn(
            request=request,
            current_user=_request_user(),
            pre_gate_classification="DOMAIN_INQUIRY",
            collect_progress=True,
        )

    graph_provider.assert_awaited_once()
    assert fake_graph.graph_input is not None
    assert fake_graph.graph_input.pending_message == "danke"
    assert fake_graph.config == {
        "configurable": {"thread_id": "sealai:tenant-1:user-1:case-stream"}
    }
    assert fake_graph.stream_mode == ["values", "updates", "custom"]
    assert result.result_state.output_reply.startswith("Gern.")
    assert result.persisted_state is persisted_state


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
    persist = AsyncMock()
    with (
        patch("app.agent.api.streaming.run_governed_graph_turn", seam),
        patch("app.agent.api.streaming._persist_live_governed_state", persist),
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
        progress_callback=ANY,
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
    assert payloads[1]["reply"] == "Bitte Medium angeben."
    assert payloads[1]["answer_markdown"] == payloads[1]["reply"]
    assert payloads[1]["response_class"] == "structured_clarification"
    persist.assert_awaited_once()
    persisted_state_arg = persist.await_args.kwargs["state"]
    assert persist.await_args.kwargs["session_id"] == "case-sse"
    assert persist.await_args.kwargs["pre_gate_classification"] == "DOMAIN_INQUIRY"
    assert persisted_state_arg.conversation_messages[-1] == ConversationMessage(
        role="assistant",
        content="Bitte Medium angeben.",
    )
    assert frames[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_sse_governed_path_forwards_langgraph_native_answer_tokens() -> None:
    result_state = GraphState(
        output_reply="Fallback",
        output_answer_markdown="Native Antwort.",
        output_answer_markdown_source="governed_composer",
        output_response_class="structured_clarification",
    )
    persisted_state = GovernedSessionState()
    seam = AsyncMock(
        return_value=GovernedGraphTurnResult(
            result_state=result_state,
            persisted_state=persisted_state,
            progress_events=[
                {
                    "event_type": "governed_answer_text_chunk",
                    "type": "text_chunk",
                    "text": "Native ",
                },
                {
                    "event_type": "governed_answer_text_chunk",
                    "type": "text_chunk",
                    "text": "Antwort.",
                },
            ],
        )
    )

    request = SimpleNamespace(session_id="case-native-stream", message="Ich brauche eine Dichtung")
    with (
        patch("app.agent.api.streaming.run_governed_graph_turn", seam),
        patch("app.agent.api.streaming._persist_live_governed_state", AsyncMock()),
        patch("app.agent.api.streaming.GovernedAnswerComposer.stream") as legacy_stream,
    ):
        frames = [
            frame
            async for frame in streaming._stream_governed_graph(
                request,
                current_user=_request_user(),
                pre_gate_classification="DOMAIN_INQUIRY",
            )
        ]

    payloads = [
        json.loads(frame[6:].strip())
        for frame in frames
        if frame.startswith("data: ") and not frame.startswith("data: [DONE]")
    ]
    assert [payload["text"] for payload in payloads if payload["type"] == "text_chunk"] == [
        "Native ",
        "Antwort.",
    ]
    assert next(payload for payload in payloads if payload["type"] == "state_update")[
        "answer_markdown"
    ] == "Native Antwort."
    legacy_stream.assert_not_called()


@pytest.mark.asyncio
async def test_sse_governed_path_streams_composer_chunks_before_state_update() -> None:
    from app.agent.communication.governed_answer_composer import (  # noqa: PLC0415
        GovernedAnswerComposerOutput,
        GovernedAnswerComposerStreamEvent,
    )
    from app.agent.communication.governed_answer_context import GovernedAnswerContext  # noqa: PLC0415

    governed_context = GovernedAnswerContext(
        latest_user_message="Ich brauche eine Dichtung",
        response_class="structured_clarification",
        next_best_question="Welches Medium liegt an?",
    )
    result_state = GraphState(
        output_reply="Bitte Medium angeben.",
        output_response_class="structured_clarification",
        governed_answer_context=governed_context.model_dump(mode="python"),
    )
    persisted_state = GovernedSessionState()
    seam = AsyncMock(
        return_value=GovernedGraphTurnResult(
            result_state=result_state,
            persisted_state=persisted_state,
            progress_events=[],
        )
    )

    async def fake_stream(self, request):  # noqa: ANN001
        yield GovernedAnswerComposerStreamEvent(event_type="chunk", text="Slotfrage")
        yield GovernedAnswerComposerStreamEvent(event_type="reset")
        yield GovernedAnswerComposerStreamEvent(event_type="chunk", text="Gern. ")
        yield GovernedAnswerComposerStreamEvent(
            event_type="chunk",
            text="Welches Medium liegt an?",
        )
        yield GovernedAnswerComposerStreamEvent(
            event_type="final",
            output=GovernedAnswerComposerOutput(
                answer_markdown="Gern. Welches Medium liegt an?",
            ),
        )

    request = SimpleNamespace(session_id="case-sse", message="Ich brauche eine Dichtung")
    with (
        patch("app.agent.api.streaming.run_governed_graph_turn", seam),
        patch("app.agent.api.streaming._persist_live_governed_state", AsyncMock()),
        patch("app.agent.api.streaming.is_governed_answer_composer_enabled", return_value=True),
        patch("app.agent.api.streaming.GovernedAnswerComposer.stream", fake_stream),
    ):
        frames = [
            frame
            async for frame in streaming._stream_governed_graph(
                request,
                current_user=_request_user(),
                pre_gate_classification="DOMAIN_INQUIRY",
            )
        ]

    payloads = [
        json.loads(frame[6:].strip())
        for frame in frames
        if frame.startswith("data: ") and not frame.startswith("data: [DONE]")
    ]
    assert [payload["text"] for payload in payloads if payload["type"] == "text_chunk"] == [
        "Slotfrage",
        "Gern. ",
        "Welches Medium liegt an?",
    ]
    assert any(payload["type"] == "text_reset" for payload in payloads)
    state_update = next(payload for payload in payloads if payload["type"] == "state_update")
    assert state_update["answer_markdown"] == "Gern. Welches Medium liegt an?"
    assert state_update["run_meta"]["answer_trace"]["answer_markdown_source"] == "governed_composer"


@pytest.mark.asyncio
async def test_post_graph_commit_persists_v92_and_medium_intelligence_slices() -> None:
    existing_state = GovernedSessionState()
    result_state = GraphState(
        challenge=ChallengeState(status="ready"),
        seal_system=SealSystemState(status="partial", seal_type="radial_shaft_seal"),
        engineering=EngineeringState(status="partial", route="rwdr"),
        calculation=CalculationState(status="blocked", blocked_calculations=["rwdr"]),
        dossier=DossierState(status="blocked", blockers=["manufacturer_review_required"]),
        medium_intelligence={
            "capability_id": "medium_intelligence",
            "validation_status": "registry_grounded",
            "confidence": "high",
        },
    )
    persist = AsyncMock()

    with (
        patch(
            "app.agent.api.loaders._load_live_governed_state",
            AsyncMock(return_value=existing_state),
        ),
        patch("app.agent.api.loaders._persist_live_governed_state", persist),
    ):
        updated = await _update_governed_state_post_graph(
            current_user=_request_user(),
            session_id="case-v92",
            result_state=result_state,
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert updated.challenge.status == "ready"
    assert updated.seal_system.seal_type == "radial_shaft_seal"
    assert updated.engineering.route == "rwdr"
    assert updated.calculation.blocked_calculations == ["rwdr"]
    assert updated.dossier.blockers == ["manufacturer_review_required"]
    assert updated.medium_intelligence["validation_status"] == "registry_grounded"
    persist.assert_awaited_once()
    assert persist.await_args.kwargs["state"].engineering.route == "rwdr"
