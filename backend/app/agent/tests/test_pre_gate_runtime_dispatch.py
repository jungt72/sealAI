from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.api.router import (
    chat_endpoint,
    event_generator,
    _resolve_runtime_dispatch,
    _runtime_mode_for_pre_gate,
)
from app.agent.state.models import (
    ConversationMessage,
    GovernedSessionState,
    ObservedExtraction,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.services.auth.dependencies import RequestUser
from app.services.knowledge_case_bridge_service import (
    KnowledgeConversationTurn,
    KnowledgeSessionContext,
    ParameterSeed,
)


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


def _mock_light_response(session_id: str, text: str = "LLM conversation answer") -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        reply=text,
        answer_markdown=text,
        response_class="conversational_answer",
        policy_path="conversation",
        run_meta={
            "answer_trace": {
                "reply_source": "light_conversation",
                "answer_markdown_source": "light_conversation",
                "final_visible_source": "answer_markdown",
                "composer_attempted": True,
            }
        },
        structured_state=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, classification, runtime_mode",
    [
        ("Hallo", PreGateClassification.GREETING, "CONVERSATION"),
        ("Was kann SeaLAI?", PreGateClassification.META_QUESTION, "CONVERSATION"),
        ("Was wollte ich von dir?", PreGateClassification.META_QUESTION, "CONVERSATION"),
        ("Worum ging es gerade?", PreGateClassification.META_QUESTION, "CONVERSATION"),
        ("Was ist PTFE?", PreGateClassification.KNOWLEDGE_QUERY, "CONVERSATION"),
        ("infos zu NBR", PreGateClassification.KNOWLEDGE_QUERY, "CONVERSATION"),
        ("NBR", PreGateClassification.KNOWLEDGE_QUERY, "CONVERSATION"),
        (
            "Warum ist PTFE in meinem Fall kritisch?",
            PreGateClassification.DEEP_DIVE,
            "CONVERSATION",
        ),
        (
            "Bitte gebe mir detaillierte Informationen über PTFE",
            PreGateClassification.KNOWLEDGE_QUERY,
            "CONVERSATION",
        ),
        (
            "Welchen Hersteller empfiehlst du?",
            PreGateClassification.BLOCKED,
            "CONVERSATION",
        ),
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
    expected_gate_route = (
        "CONVERSATION"
        if classification
        not in {PreGateClassification.KNOWLEDGE_QUERY, PreGateClassification.DEEP_DIVE}
        else runtime_mode
    )
    assert dispatch.gate_route == expected_gate_route
    assert dispatch.gate_applied is False
    assert dispatch.gate_reason.startswith(("pre_gate:", "pre_gate_llm_fast_responder:"))
    if classification in {
        PreGateClassification.META_QUESTION,
        PreGateClassification.GREETING,
    }:
        assert dispatch.fast_response is None
        assert dispatch.knowledge_response is None
        assert dispatch.runtime_action is not None
    elif classification is PreGateClassification.BLOCKED:
        assert dispatch.fast_response is not None
        assert dispatch.fast_response.no_case_created is True
        assert dispatch.fast_response.source_classification is classification
        assert dispatch.knowledge_response is None
    elif classification in {
        PreGateClassification.KNOWLEDGE_QUERY,
        PreGateClassification.DEEP_DIVE,
    }:
        assert dispatch.fast_response is None
        assert dispatch.knowledge_response is not None
        assert dispatch.knowledge_response.no_case_created is True
        assert dispatch.knowledge_response.source_classification is classification
    else:
        assert dispatch.fast_response is None
        assert dispatch.knowledge_response is None


def test_pre_gate_adapter_keeps_three_mode_gate_values_separate() -> None:
    assert (
        _runtime_mode_for_pre_gate(PreGateClassification.GREETING.value)
        == "CONVERSATION"
    )
    assert (
        _runtime_mode_for_pre_gate(PreGateClassification.META_QUESTION.value)
        == "CONVERSATION"
    )
    assert (
        _runtime_mode_for_pre_gate(PreGateClassification.KNOWLEDGE_QUERY.value)
        == "GOVERNED"
    )
    assert (
        _runtime_mode_for_pre_gate(PreGateClassification.DEEP_DIVE.value) == "GOVERNED"
    )
    assert (
        _runtime_mode_for_pre_gate(PreGateClassification.RECOVERY.value) == "GOVERNED"
    )
    assert (
        _runtime_mode_for_pre_gate(PreGateClassification.BLOCKED.value)
        == "CONVERSATION"
    )
    assert (
        _runtime_mode_for_pre_gate(PreGateClassification.DOMAIN_INQUIRY.value)
        == "GOVERNED"
    )


@pytest.mark.asyncio
async def test_domain_inquiry_dispatch_goes_directly_to_governed_without_second_gate(
    monkeypatch,
) -> None:
    gate_decider = AsyncMock(
        side_effect=AssertionError("domain inquiry must not hit second gate")
    )
    load_state = AsyncMock(return_value=None)

    monkeypatch.setattr("app.agent.runtime.gate.decide_route_async", gate_decider)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Wir brauchen eine PTFE-Dichtung fuer eine Pumpe bei 12 bar und 180 C.",
            session_id="domain-direct-governed",
        ),
        current_user=_user(),
    )

    assert (
        dispatch.pre_gate_classification == PreGateClassification.DOMAIN_INQUIRY.value
    )
    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.gate_route == "GOVERNED"
    assert dispatch.gate_applied is False
    assert dispatch.gate_reason == "pre_gate:deterministic_domain_inquiry"
    assert dispatch.fast_response is None
    assert dispatch.knowledge_response is None
    gate_decider.assert_not_awaited()
    load_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_fast_responder_chat_path_does_not_invoke_graph_or_persist(
    monkeypatch,
) -> None:
    async def fake_light_runtime(*args, **kwargs):
        return _mock_light_response("fast-no-persist", "SeaLAI hilft dir, Dichtungsfragen sauber zu strukturieren.")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Fast Responder must not persist state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Fast Responder must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fake_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    response = await chat_endpoint(
        ChatRequest(message="Was kann SeaLAI?", session_id="fast-no-persist"),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    assert "fast_responder" not in response.run_meta
    assert response.run_meta["answer_trace"]["reply_source"] == "light_conversation"
    assert response.run_meta["answer_trace"]["answer_markdown_source"] == "light_conversation"
    assert response.run_meta["answer_trace"]["composer_attempted"] is True
    assert response.structured_state is None


@pytest.mark.asyncio
async def test_greeting_chat_path_uses_fast_responder_without_case_persistence(
    monkeypatch,
) -> None:
    async def fake_light_runtime(*args, **kwargs):
        return _mock_light_response("greeting-no-case", "Hallo, schoen dass du da bist.")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Greeting must not persist governed state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Greeting must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fake_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    response = await chat_endpoint(
        ChatRequest(message="Hallo", session_id="greeting-no-case"),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    assert "schoen" in response.reply.lower()
    assert "fast_responder" not in response.run_meta
    assert response.run_meta["answer_trace"]["reply_source"] == "light_conversation"
    assert response.run_meta["answer_trace"]["composer_attempted"] is True
    assert response.structured_state is None


@pytest.mark.asyncio
async def test_bare_compound_greeting_uses_fast_responder_without_case_persistence(
    monkeypatch,
) -> None:
    async def fake_light_runtime(*args, **kwargs):
        return _mock_light_response("bare-greeting-no-case", "Guten Morgen, ich bin da.")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Bare greeting must not persist governed state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Bare greeting must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fake_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    response = await chat_endpoint(
        ChatRequest(
            message="Hallo und guten morgen", session_id="bare-greeting-no-case"
        ),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    assert "fast_responder" not in response.run_meta
    assert response.run_meta["answer_trace"]["reply_source"] == "light_conversation"
    assert response.structured_state is None
    assert "welches medium" not in response.reply.lower()


@pytest.mark.asyncio
async def test_greeting_plus_smalltalk_routes_to_conversation_runtime() -> None:
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Hallo, wie geht es dir?", session_id="greeting-smalltalk"),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == PreGateClassification.GREETING.value
    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.fast_response is None
    assert dispatch.gate_reason.startswith("pre_gate_llm_fast_responder:")
    assert dispatch.knowledge_response is None


@pytest.mark.asyncio
async def test_social_conversation_with_typo_uses_fast_responder_without_graph(
    monkeypatch,
) -> None:
    async def fake_light_runtime(*args, **kwargs):
        return _mock_light_response("social-typo-no-case", "Guten Morgen, mir geht es gut.")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Social conversation must not persist governed state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Social conversation must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fake_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    response = await chat_endpoint(
        ChatRequest(
            message="Guten MNorgen, wie geht es dir heute morgen?",
            session_id="social-typo-no-case",
        ),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    assert "fast_responder" not in response.run_meta
    assert response.run_meta["answer_trace"]["reply_source"] == "light_conversation"
    assert response.structured_state is None
    assert "welches medium" not in response.reply.lower()


@pytest.mark.asyncio
async def test_social_conversation_dispatch_with_typo_does_not_enter_governed() -> None:
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Guten MNorgen, wie geht es dir heute morgen?",
            session_id="social-typo-dispatch",
        ),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == PreGateClassification.GREETING.value
    assert dispatch.gate_reason == "pre_gate_llm_fast_responder:deterministic_social_conversation"
    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.fast_response is None
    assert dispatch.governed_state is None
    assert dispatch.knowledge_response is None


@pytest.mark.asyncio
async def test_social_conversation_colloquial_wellbeing_does_not_enter_governed() -> (
    None
):
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="moin, wie läufts heute bei dir?",
            session_id="social-colloquial-dispatch",
        ),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == PreGateClassification.GREETING.value
    assert dispatch.gate_reason == "pre_gate_llm_fast_responder:deterministic_social_conversation"
    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.fast_response is None
    assert dispatch.governed_state is None
    assert dispatch.knowledge_response is None


@pytest.mark.asyncio
async def test_knowledge_chat_path_uses_knowledge_service_without_case_creation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false")

    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Knowledge query must not enter light runtime")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Knowledge query must not persist state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Knowledge query must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fail_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    response = await chat_endpoint(
        ChatRequest(message="Was ist PTFE?", session_id="knowledge-no-case"),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    assert response.policy_path == "knowledge"
    assert (
        response.run_meta["knowledge_service"]["source_classification"]
        == "KNOWLEDGE_QUERY"
    )
    assert response.run_meta["knowledge_service"]["no_case_created"] is True
    assert response.run_meta["knowledge_service"]["citations"]
    assert response.run_meta["answer_trace"]["reply_source"] == "knowledge_service"
    assert (
        response.run_meta["answer_trace"]["answer_markdown_source"]
        == "knowledge_service"
    )
    assert response.run_meta["answer_trace"]["composer_attempted"] is False
    assert response.structured_state is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "Vergleiche FKM und EPDM für Dichtungen.",
        "Wann nimmt man EPDM statt FKM?",
        "PTFE vs FKM",
        "und fkm mit nbr?",
        "FKM mit NBR?",
    ],
)
async def test_material_comparison_dispatch_uses_knowledge_without_case_creation(
    monkeypatch,
    message: str,
) -> None:
    load_state = AsyncMock(return_value=None)
    load_context = AsyncMock(return_value=None)
    save_context = AsyncMock()

    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context", load_context
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context", save_context
    )

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message=message, session_id="material-comparison-no-case"),
        current_user=_user(),
    )

    assert (
        dispatch.pre_gate_classification == PreGateClassification.KNOWLEDGE_QUERY.value
    )
    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.knowledge_response is not None
    assert dispatch.knowledge_response.no_case_created is True
    assert dispatch.fast_response is None
    assert dispatch.governed_state is None
    load_state.assert_awaited_once_with(
        current_user=_user(),
        session_id="material-comparison-no-case",
        create_if_missing=False,
    )


@pytest.mark.asyncio
async def test_material_comparison_chat_path_emits_safe_debug_trace_without_case_mutation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false")

    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Material comparison must not enter light runtime")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Material comparison must not persist governed state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Material comparison must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fail_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )

    response = await chat_endpoint(
        ChatRequest(
            message="Vergleiche FKM und EPDM für Dichtungen.",
            session_id="material-debug",
        ),
        current_user=_user(),
    )

    assert response.policy_path == "knowledge"
    assert response.proposed_case_delta is None
    assert response.answer_markdown == response.reply
    assert (
        response.run_meta["knowledge_service"]["source_classification"]
        == "KNOWLEDGE_QUERY"
    )
    assert (
        response.run_meta["knowledge_debug"]["answer_markdown_source"]
        == "reply_passthrough"
    )
    assert response.run_meta["knowledge_debug"]["composer_attempted"] is False
    assert response.run_meta["answer_trace"]["reply_source"] == "knowledge_service"
    assert (
        response.run_meta["answer_trace"]["answer_markdown_source"]
        == "knowledge_service"
    )
    assert response.run_meta["answer_trace"]["composer_attempted"] is False


@pytest.mark.asyncio
async def test_deep_dive_chat_path_uses_knowledge_service_without_case_creation(
    monkeypatch,
) -> None:
    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Deep dive must not enter light runtime")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Deep dive must not persist governed state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Deep dive must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fail_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    response = await chat_endpoint(
        ChatRequest(
            message="Warum ist PTFE in meinem Fall kritisch?",
            session_id="deep-dive-no-case",
        ),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    assert response.policy_path == "knowledge"
    assert (
        response.run_meta["knowledge_service"]["source_classification"] == "DEEP_DIVE"
    )
    assert response.run_meta["knowledge_service"]["no_case_created"] is True
    assert response.structured_state is None


@pytest.mark.asyncio
async def test_knowledge_query_dispatch_persists_only_transient_bridge_context(
    monkeypatch,
) -> None:
    load_context = AsyncMock(return_value=None)
    save_context = AsyncMock()

    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context", load_context
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context", save_context
    )

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Was ist PTFE bei 180 C und 12 bar Dampf?",
            session_id="knowledge-bridge",
        ),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.knowledge_response is not None
    assert dispatch.knowledge_response.no_case_created is True
    load_context.assert_awaited_once()
    save_context.assert_awaited_once()
    saved_context = save_context.await_args.kwargs["context"]
    assert saved_context.mentioned_parameters["temperature_c"].raw_value == 180.0
    assert saved_context.mentioned_parameters["pressure_bar"].raw_value == 12.0
    assert saved_context.conversation_turns[-1].role == "assistant"


@pytest.mark.asyncio
async def test_domain_inquiry_chat_path_stays_governed_and_keeps_reply_contract(
    monkeypatch,
) -> None:
    governed_response = await chat_endpoint(
        ChatRequest(message="Was ist PTFE?", session_id="knowledge-fixture"),
        current_user=_user(),
    )

    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Domain inquiry must not enter light runtime")

    governed_runner = AsyncMock(return_value=governed_response)

    monkeypatch.setattr(
        "app.agent.runtime.gate.decide_route_async",
        AsyncMock(side_effect=AssertionError("second gate must not be used")),
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fail_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", governed_runner
    )

    response = await chat_endpoint(
        ChatRequest(
            message="Ich brauche eine Wellendichtung fuer 10 bar und 3000 rpm.",
            session_id="domain-json",
        ),
        current_user=_user(),
    )

    assert response.response_class == "conversational_answer"
    governed_runner.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_dispatch_stays_governed_without_fast_or_knowledge_path(
    monkeypatch,
) -> None:
    gate_decider = AsyncMock(
        side_effect=AssertionError("recovery must not hit second gate")
    )
    load_state = AsyncMock(return_value=None)

    monkeypatch.setattr("app.agent.runtime.gate.decide_route_async", gate_decider)
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Das stimmt nicht, gemeint war Ethanol.",
            session_id="recovery-governed",
        ),
        current_user=_user(),
    )

    assert dispatch.pre_gate_classification == PreGateClassification.RECOVERY.value
    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.gate_route == "GOVERNED"
    assert dispatch.gate_applied is False
    assert dispatch.gate_reason == "pre_gate:deterministic_recovery"
    assert dispatch.fast_response is None
    assert dispatch.knowledge_response is None
    gate_decider.assert_not_awaited()
    load_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_domain_inquiry_dispatch_seeds_governed_state_from_knowledge_context(
    monkeypatch,
) -> None:
    knowledge_context = KnowledgeSessionContext(
        session_id="domain-bridge",
        mentioned_parameters={
            "pressure_bar": ParameterSeed(
                field_name="pressure_bar",
                raw_value=12.0,
                raw_unit="bar",
                confidence=0.92,
                source_turn_index=1,
            ),
            "medium": ParameterSeed(
                field_name="medium",
                raw_value="Dampf",
                confidence=0.85,
                source_turn_index=1,
            ),
        },
        conversation_turns=(
            KnowledgeConversationTurn(
                role="user", content="Was ist PTFE bei 12 bar Dampf?"
            ),
            KnowledgeConversationTurn(
                role="assistant", content="PTFE ist dafuer temperaturstabil."
            ),
        ),
        explored_concepts=("PTFE", "Dampf"),
        user_turn_index=1,
    )
    seeded_state = GovernedSessionState(
        conversation_messages=[
            ConversationMessage(role="user", content="Was ist PTFE bei 12 bar Dampf?"),
            ConversationMessage(
                role="assistant", content="PTFE ist dafuer temperaturstabil."
            ),
        ],
        observed=GovernedSessionState().observed.with_extraction(
            ObservedExtraction(
                field_name="pressure_bar",
                raw_value=12.0,
                raw_unit="bar",
                source="user",
                confidence=0.92,
                turn_index=1,
            )
        ),
        user_turn_index=1,
    )
    bridge_context_loader = AsyncMock(return_value=knowledge_context)
    bridge_loader = AsyncMock(return_value=seeded_state)
    load_state = AsyncMock(
        side_effect=AssertionError("plain governed load must not win over bridge seed")
    )

    monkeypatch.setattr(
        "app.agent.runtime.gate.decide_route_async",
        AsyncMock(side_effect=AssertionError("second gate must not be used")),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        bridge_context_loader,
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._bridge_knowledge_session_to_governed_state",
        bridge_loader,
    )
    monkeypatch.setattr("app.agent.api.dispatch._load_live_governed_state", load_state)

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Ich brauche dafuer jetzt eine Loesung fuer meine Pumpe.",
            session_id="domain-bridge",
        ),
        current_user=_user(),
    )

    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.governed_state is seeded_state
    assert dispatch.gate_reason == "pre_gate:ambiguous_fail_safe_domain_inquiry"
    bridge_context_loader.assert_awaited_once()
    bridge_loader.assert_awaited_once_with(
        current_user=_user(),
        session_id="domain-bridge",
        context=knowledge_context,
    )


@pytest.mark.asyncio
async def test_fast_responder_stream_path_does_not_invoke_graph_or_persist(
    monkeypatch,
) -> None:
    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Fast Responder must not enter light runtime")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Fast Responder must not persist state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Fast Responder must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.streaming._stream_light_runtime", fail_light_runtime
    )
    monkeypatch.setattr("app.agent.api.streaming._stream_governed_graph", fail_governed)
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    frames = [
        frame
        async for frame in event_generator(
            ChatRequest(
                message="Welchen Hersteller empfiehlst du?", session_id="fast-stream"
            ),
            current_user=_user(),
        )
    ]

    assert len(frames) == 2
    assert '"source_classification": "BLOCKED"' in frames[0]
    assert '"no_case_created": true' in frames[0]
    assert '"answer_trace"' in frames[0]
    assert '"reply_source": "fast_responder"' in frames[0]
    assert frames[1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_domain_inquiry_stream_path_stays_governed_and_keeps_sse_contract(
    monkeypatch,
) -> None:
    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Domain inquiry stream must not enter light runtime")

    async def stub_governed_stream(*args, **kwargs):
        yield 'data: {"type": "state_update", "reply": "governed"}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(
        "app.agent.runtime.gate.decide_route_async",
        AsyncMock(side_effect=AssertionError("second gate must not be used")),
    )
    monkeypatch.setattr(
        "app.agent.api.streaming._stream_light_runtime", fail_light_runtime
    )
    monkeypatch.setattr(
        "app.agent.api.streaming._stream_governed_graph", stub_governed_stream
    )

    frames = [
        frame
        async for frame in event_generator(
            ChatRequest(
                message="Wir suchen eine Dichtung fuer Getriebe bei 15 bar.",
                session_id="domain-stream",
            ),
            current_user=_user(),
        )
    ]

    assert frames == [
        'data: {"type": "state_update", "reply": "governed"}\n\n',
        "data: [DONE]\n\n",
    ]


@pytest.mark.asyncio
async def test_knowledge_stream_path_uses_knowledge_service_without_case_creation(
    monkeypatch,
) -> None:
    async def fail_light_runtime(*args, **kwargs):
        raise AssertionError("Knowledge stream must not enter light runtime")

    async def fail_persist(*args, **kwargs):
        raise AssertionError("Knowledge stream must not persist state")

    async def fail_governed(*args, **kwargs):
        raise AssertionError("Knowledge stream must not invoke governed graph")

    monkeypatch.setattr(
        "app.agent.api.streaming._stream_light_runtime", fail_light_runtime
    )
    monkeypatch.setattr("app.agent.api.streaming._stream_governed_graph", fail_governed)
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )

    frames = [
        frame
        async for frame in event_generator(
            ChatRequest(message="Was ist PTFE?", session_id="knowledge-stream"),
            current_user=_user(),
        )
    ]

    assert len(frames) == 2
    assert '"policy_path": "knowledge"' in frames[0]
    assert '"source_classification": "KNOWLEDGE_QUERY"' in frames[0]
    assert '"no_case_created": true' in frames[0]
    assert '"answer_trace"' in frames[0]
    assert '"reply_source": "knowledge_service"' in frames[0]
    assert frames[1] == "data: [DONE]\n\n"
