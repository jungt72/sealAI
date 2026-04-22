from __future__ import annotations

import pytest

from app.agent.api.models import ChatRequest
from app.agent.api.router import chat_endpoint, event_generator, _resolve_runtime_dispatch, _runtime_mode_for_pre_gate
from app.domain.pre_gate_classification import PreGateClassification
from app.services.auth.dependencies import RequestUser


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, classification, runtime_mode",
    [
        ("Hallo", PreGateClassification.GREETING, "CONVERSATION"),
        ("Was kann SeaLAI?", PreGateClassification.META_QUESTION, "CONVERSATION"),
        ("Was ist FKM?", PreGateClassification.KNOWLEDGE_QUERY, "EXPLORATION"),
        ("Welchen Hersteller empfiehlst du?", PreGateClassification.BLOCKED, "CONVERSATION"),
    ],
)
async def test_runtime_dispatch_uses_pre_gate_before_three_mode_gate(
    message: str,
    classification: PreGateClassification,
    runtime_mode: str,
) -> None:
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message=message, session_id="pre-gate-test"),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == classification.value
    assert dispatch.runtime_mode == runtime_mode
    assert dispatch.gate_route == runtime_mode
    assert dispatch.gate_applied is False
    assert dispatch.gate_reason.startswith("pre_gate:")
    if classification in {
        PreGateClassification.GREETING,
        PreGateClassification.META_QUESTION,
        PreGateClassification.BLOCKED,
    }:
        assert dispatch.fast_response is not None
        assert dispatch.fast_response.no_case_created is True
    else:
        assert dispatch.fast_response is None


def test_pre_gate_adapter_keeps_three_mode_gate_values_separate() -> None:
    assert _runtime_mode_for_pre_gate(PreGateClassification.GREETING.value) == "CONVERSATION"
    assert _runtime_mode_for_pre_gate(PreGateClassification.META_QUESTION.value) == "CONVERSATION"
    assert _runtime_mode_for_pre_gate(PreGateClassification.KNOWLEDGE_QUERY.value) == "EXPLORATION"
    assert _runtime_mode_for_pre_gate(PreGateClassification.BLOCKED.value) == "CONVERSATION"
    assert _runtime_mode_for_pre_gate(PreGateClassification.DOMAIN_INQUIRY.value) == "GOVERNED"


@pytest.mark.asyncio
async def test_fast_responder_chat_path_does_not_invoke_graph_or_persist(monkeypatch) -> None:
    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Fast Responder must not enter light runtime")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Fast Responder must not persist state")

    class Graph:
        async def ainvoke(self, *args, **kwargs):
            raise AssertionError("Fast Responder must not invoke graph")

        def astream(self, *args, **kwargs):
            raise AssertionError("Fast Responder must not stream graph")

    monkeypatch.setattr("app.agent.api.router._run_light_chat_response", fail_light_runtime)
    monkeypatch.setattr("app.agent.api.router._persist_live_governed_state", fail_persist)
    monkeypatch.setattr("app.agent.api.router.GOVERNED_GRAPH", Graph())

    response = await chat_endpoint(
        ChatRequest(message="Hallo", session_id="fast-no-persist"),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    assert response.run_meta["fast_responder"]["source_classification"] == "GREETING"
    assert response.run_meta["fast_responder"]["no_case_created"] is True
    assert response.structured_state is None


@pytest.mark.asyncio
async def test_fast_responder_stream_path_does_not_invoke_graph_or_persist(monkeypatch) -> None:
    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Fast Responder must not enter light runtime")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Fast Responder must not persist state")

    class Graph:
        async def ainvoke(self, *args, **kwargs):
            raise AssertionError("Fast Responder must not invoke graph")

        def astream(self, *args, **kwargs):
            raise AssertionError("Fast Responder must not stream graph")

    monkeypatch.setattr("app.agent.api.router._run_light_chat_response", fail_light_runtime)
    monkeypatch.setattr("app.agent.api.router._persist_live_governed_state", fail_persist)
    monkeypatch.setattr("app.agent.api.router.GOVERNED_GRAPH", Graph())

    frames = [
        frame
        async for frame in event_generator(
            ChatRequest(message="Welchen Hersteller empfiehlst du?", session_id="fast-stream"),
            current_user=_user(),
        )
    ]

    assert len(frames) == 2
    assert '"source_classification": "BLOCKED"' in frames[0]
    assert '"no_case_created": true' in frames[0]
    assert frames[1] == "data: [DONE]\n\n"
