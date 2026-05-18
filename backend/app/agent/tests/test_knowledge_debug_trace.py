from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.api.routes.chat import chat_endpoint
from app.agent.communication.answer_composer import (
    KnowledgeAnswerComposerInput,
    KnowledgeAnswerComposerOutput,
)
from app.services.auth.dependencies import RequestUser
from app.services.knowledge_case_bridge_service import (
    KnowledgeConversationTurn,
    KnowledgeSessionContext,
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


def _block_case_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_governed(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("knowledge debug trace must not invoke governed case runtime")

    async def fail_persist(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("knowledge debug trace must not persist governed case state")

    monkeypatch.setattr("app.agent.api.routes.chat._run_light_chat_response", fail_governed)
    monkeypatch.setattr("app.agent.api.routes.chat._run_governed_chat_response", fail_governed)
    monkeypatch.setattr("app.agent.api.loaders._persist_live_governed_state", fail_persist)


def _no_bridge_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )


def _knowledge_debug(response: ChatResponse) -> dict[str, Any]:
    assert response.run_meta is not None
    debug = response.run_meta.get("knowledge_debug")
    assert isinstance(debug, dict)
    return debug


@pytest.mark.asyncio
async def test_knowledge_debug_trace_disabled_keeps_existing_response_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", raising=False)
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false")
    _block_case_mutation(monkeypatch)
    _no_bridge_context(monkeypatch)

    response = await chat_endpoint(
        ChatRequest(message="Was ist PTFE?", session_id="debug-disabled"),
        current_user=_user(),
    )

    assert response.policy_path == "knowledge"
    assert response.reply
    assert response.answer_markdown == response.reply
    assert response.run_meta is not None
    assert "knowledge_debug" not in response.run_meta


@pytest.mark.asyncio
async def test_knowledge_debug_trace_enabled_with_composer_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false")
    _block_case_mutation(monkeypatch)
    _no_bridge_context(monkeypatch)

    async def fail_compose(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("composer must not run when composer flag is disabled")

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        fail_compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Was ist PTFE?", session_id="debug-composer-off"),
        current_user=_user(),
    )
    debug = _knowledge_debug(response)

    assert debug["composer_enabled"] is False
    assert debug["composer_attempted"] is False
    assert debug["composer_succeeded"] is False
    assert debug["answer_markdown_source"] == "reply_passthrough"
    assert debug["reply_source"] == "knowledge_service"
    assert debug["knowledge_mode"] == "KNOWLEDGE_QUERY"
    assert debug["route"]
    assert isinstance(debug["evidence_count"], int)
    assert isinstance(debug["history_count"], int)
    assert response.answer_markdown == response.reply

    debug_payload = json.dumps(debug, ensure_ascii=True, sort_keys=True)
    assert response.reply not in debug_payload
    assert "PTFE: Temperaturbereich" not in debug_payload
    assert "Was ist PTFE?" not in debug_payload


@pytest.mark.asyncio
async def test_knowledge_debug_trace_enabled_with_composer_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    _block_case_mutation(monkeypatch)

    async def load_context(*_args: Any, **_kwargs: Any) -> KnowledgeSessionContext:
        return KnowledgeSessionContext(
            session_id="debug-composer-success",
            conversation_turns=(
                KnowledgeConversationTurn(role="user", content="Was ist PTFE?"),
                KnowledgeConversationTurn(role="assistant", content="PTFE ist ein Fluorpolymer."),
            ),
        )

    monkeypatch.setattr("app.agent.api.dispatch._load_live_knowledge_session_context", load_context)
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )

    captured: dict[str, KnowledgeAnswerComposerInput] = {}

    async def compose(
        _self: object,
        request: KnowledgeAnswerComposerInput,
    ) -> KnowledgeAnswerComposerOutput:
        captured["request"] = request
        return KnowledgeAnswerComposerOutput(
            answer_markdown="**PTFE kurz:** Zusammengesetzte Expertenantwort.",
            confidence_note="mocked",
        )

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Was ist PTFE?", session_id="debug-composer-success"),
        current_user=_user(),
    )
    context = captured["request"].context
    debug = _knowledge_debug(response)

    assert debug["answer_markdown_source"] == "composer"
    assert debug["composer_enabled"] is True
    assert debug["composer_attempted"] is True
    assert debug["composer_succeeded"] is True
    assert debug["evidence_count"] == len(context.evidence_items)
    expected_source_types = list(dict.fromkeys(item.source_type for item in context.evidence_items))
    assert debug["evidence_source_types"] == expected_source_types
    assert "fact_card" in debug["evidence_source_types"]
    assert debug["history_count"] == len(context.recent_history)
    assert response.reply
    assert response.answer_markdown == "**PTFE kurz:** Zusammengesetzte Expertenantwort."
    assert response.answer_markdown == response.reply


@pytest.mark.asyncio
async def test_knowledge_debug_trace_enabled_with_composer_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    _block_case_mutation(monkeypatch)
    _no_bridge_context(monkeypatch)

    async def fail_compose(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("provider payload secret=abc stack trace raw answer")

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        fail_compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Was ist PTFE?", session_id="debug-composer-fallback"),
        current_user=_user(),
    )
    debug = _knowledge_debug(response)

    assert debug["answer_markdown_source"] == "composer_fallback"
    assert debug["composer_enabled"] is True
    assert debug["composer_attempted"] is True
    assert debug["composer_succeeded"] is False
    assert debug["composer_fallback_reason"] == "composer_exception"
    assert "secret" not in json.dumps(debug, ensure_ascii=True)
    assert "stack trace" not in json.dumps(debug, ensure_ascii=True)
    assert response.answer_markdown == response.reply


@pytest.mark.asyncio
async def test_knowledge_debug_trace_marks_regulatory_currentness_for_pfas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false")
    _block_case_mutation(monkeypatch)
    _no_bridge_context(monkeypatch)

    response = await chat_endpoint(
        ChatRequest(
            message="Was bedeutet PFAS fuer Dichtungen?",
            session_id="debug-pfas",
        ),
        current_user=_user(),
    )
    debug = _knowledge_debug(response)

    assert debug["regulatory_currentness_required"] is True
    assert debug["limitations_count"] > 0


@pytest.mark.asyncio
async def test_knowledge_debug_trace_serializes_only_safe_bounded_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    _block_case_mutation(monkeypatch)
    _no_bridge_context(monkeypatch)

    async def compose(
        _self: object,
        _request: KnowledgeAnswerComposerInput,
    ) -> KnowledgeAnswerComposerOutput:
        return KnowledgeAnswerComposerOutput(
            answer_markdown="**PTFE sicher gerahmt:** Kompakte Ausgabe.",
            confidence_note=None,
        )

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    user_message = "Was ist PTFE?"
    response = await chat_endpoint(
        ChatRequest(message=user_message, session_id="debug-safety"),
        current_user=_user(),
    )
    debug = _knowledge_debug(response)
    payload = json.dumps(debug, ensure_ascii=True, sort_keys=True)
    trace = response.run_meta.get("answer_trace")
    assert isinstance(trace, dict)
    trace_payload = json.dumps(trace, ensure_ascii=True, sort_keys=True)

    assert user_message not in payload
    assert response.reply not in payload
    assert str(response.answer_markdown) not in payload
    assert "PTFE: Temperaturbereich" not in payload
    assert "knowledge-card" not in payload
    assert "source_id" not in payload
    assert "evidence_ref" not in payload
    assert "embedding" not in payload
    assert "traceback" not in payload.lower()
    assert "stack" not in payload.lower()
    assert user_message not in trace_payload
    assert response.reply not in trace_payload
    assert str(response.answer_markdown) not in trace_payload
    assert "source_id" not in trace_payload
    assert "evidence_ref" not in trace_payload
    assert "embedding" not in trace_payload
    assert "traceback" not in trace_payload.lower()
    assert "stack" not in trace_payload.lower()
    assert "secret" not in trace_payload.lower()


@pytest.mark.asyncio
async def test_knowledge_debug_trace_does_not_pollute_fast_or_governed_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")

    fast_response = await chat_endpoint(
        ChatRequest(message="Hallo", session_id="debug-fast"),
        current_user=_user(),
    )

    assert fast_response.run_meta is not None
    assert "knowledge_debug" not in fast_response.run_meta

    async def governed_stub(*_args: Any, **_kwargs: Any) -> ChatResponse:
        return ChatResponse(
            session_id="debug-governed",
            reply="governed",
            answer_markdown="governed",
            policy_path="governed",
            response_class="structured_clarification",
            run_meta={"version_provenance": {"test": True}},
        )

    monkeypatch.setattr("app.agent.api.routes.chat._run_governed_chat_response", governed_stub)

    governed_response = await chat_endpoint(
        ChatRequest(
            message="Wir brauchen eine Dichtung fuer Getriebeoel bei 80 Grad.",
            session_id="debug-governed",
        ),
        current_user=_user(),
    )

    assert governed_response.run_meta is not None
    assert "knowledge_debug" not in governed_response.run_meta
