from __future__ import annotations

import logging

import pytest

from app.agent.api.models import ChatRequest
from app.agent.api.dispatch import _compose_knowledge_answer_if_enabled
from app.agent.api.routes.chat import chat_endpoint
from app.agent.communication.answer_composer import (
    KnowledgeAnswerComposer,
    KnowledgeAnswerComposerOutput,
    KnowledgeAnswerComposerInput,
    build_knowledge_answer_composer_messages,
)
from app.agent.communication.knowledge_context_builder import KnowledgeContextBuilder
from app.services.auth.dependencies import RequestUser
from app.services.knowledge_service import KnowledgeService
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
    async def fail_governed(*_args, **_kwargs):
        raise AssertionError("knowledge composer path must not invoke governed case runtime")

    async def fail_persist(*_args, **_kwargs):
        raise AssertionError("knowledge composer path must not persist governed case state")

    monkeypatch.setattr("app.agent.api.routes.chat._run_governed_chat_response", fail_governed)
    monkeypatch.setattr("app.agent.api.routes.chat._run_light_chat_response", fail_governed)
    monkeypatch.setattr("app.agent.api.loaders._persist_live_governed_state", fail_persist)


def _answer_trace(response) -> dict:
    assert response.run_meta is not None
    trace = response.run_meta.get("answer_trace")
    assert isinstance(trace, dict)
    return trace


class _FactcardStore:
    _sources = {"src-1": {"title": "Curated source"}}

    def __init__(self, cards: list[dict[str, object]]) -> None:
        self._cards = cards

    def match_query_to_cards(self, query_lower: str) -> list[dict[str, object]]:
        return list(self._cards)


@pytest.mark.asyncio
async def test_knowledge_answer_composer_disabled_keeps_deterministic_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", raising=False)
    _block_case_mutation(monkeypatch)

    async def fail_compose(*_args, **_kwargs):
        raise AssertionError("composer must not run when feature flag is disabled")

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        fail_compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Vergleich PTFE und FKM", session_id="composer-off"),
        current_user=_user(),
    )

    assert response.policy_path == "knowledge"
    assert response.reply
    assert response.answer_markdown == response.reply
    assert response.proposed_case_delta is None
    trace = _answer_trace(response)
    assert trace["reply_source"] == "knowledge_service"
    assert trace["answer_markdown_source"] == "knowledge_service"
    assert trace["composer_attempted"] is False
    assert trace["composer_succeeded"] is False


@pytest.mark.asyncio
async def test_knowledge_answer_composer_enabled_keeps_reply_and_sets_answer_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    _block_case_mutation(monkeypatch)

    async def compose(_self, request: KnowledgeAnswerComposerInput):
        assert request.no_case is True
        assert "Vergleich FKM" in request.user_message
        assert request.deterministic_answer
        assert request.context.evidence_items
        return KnowledgeAnswerComposerOutput(
            answer_markdown="**Kurzvergleich:** FKM und EPDM sind unterschiedliche Elastomerfamilien.",
            confidence_note="mocked",
        )

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Vergleich FKM und EPDM fuer Dichtungen.", session_id="composer-on"),
        current_user=_user(),
    )

    assert response.policy_path == "knowledge"
    assert response.reply != response.answer_markdown
    assert response.reply
    assert "FKM und EPDM" in str(response.answer_markdown)
    assert response.proposed_case_delta is None
    trace = _answer_trace(response)
    assert trace["reply_source"] == "knowledge_service"
    assert trace["answer_markdown_source"] == "knowledge_composer"
    assert trace["composer_attempted"] is True
    assert trace["composer_succeeded"] is True


@pytest.mark.asyncio
async def test_knowledge_answer_composer_receives_enriched_history_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    _block_case_mutation(monkeypatch)

    async def load_context(*_args, **_kwargs):
        return KnowledgeSessionContext(
            session_id="composer-history",
            conversation_turns=(
                KnowledgeConversationTurn(role="user", content="Was ist PTFE?"),
                KnowledgeConversationTurn(
                    role="assistant",
                    content="PTFE ist ein Fluorpolymer.",
                ),
            ),
        )

    async def persist_context(*_args, **_kwargs):
        return None

    captured: dict[str, KnowledgeAnswerComposerInput] = {}

    async def compose(_self, request: KnowledgeAnswerComposerInput):
        captured["request"] = request
        return KnowledgeAnswerComposerOutput(
            answer_markdown="**Kontinuitaet:** Aufbauend auf PTFE: FKM ist eine andere Werkstofffamilie.",
            confidence_note=None,
        )

    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        load_context,
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context",
        persist_context,
    )
    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Was ist FKM?", session_id="composer-history"),
        current_user=_user(),
    )

    request = captured["request"]
    assert [turn.role for turn in request.context.recent_history] == ["user", "assistant"]
    assert "PTFE ist ein Fluorpolymer" in request.context.recent_history[1].content
    assert request.context.evidence_items
    assert response.reply
    assert response.answer_markdown != response.reply
    assert response.proposed_case_delta is None


@pytest.mark.asyncio
async def test_knowledge_answer_composer_receives_factcard_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    knowledge_response = KnowledgeService(
        factcard_store=_FactcardStore(
            [
                {
                    "id": "PTFE-F-001",
                    "topic": "PTFE",
                    "property": "temperature_window",
                    "value": "-200 bis 260",
                    "units": "C",
                    "source": "src-1",
                }
            ]
        )
    ).answer("PTFE Temperatur")
    captured: dict[str, KnowledgeAnswerComposerInput] = {}

    async def compose(_self, request: KnowledgeAnswerComposerInput):
        captured["request"] = request
        return KnowledgeAnswerComposerOutput(
            answer_markdown="**PTFE:** Temperaturhinweis aus kuratierter Evidenz.",
            confidence_note=None,
        )

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await _compose_knowledge_answer_if_enabled(
        user_message="PTFE Temperatur",
        knowledge_response=knowledge_response,
        conversation_route=None,
    )

    request = captured["request"]
    assert request.context.evidence_items[0].source_type == "fact_card"
    assert "PTFE: Temperaturbereich" in request.context.evidence_items[0].content
    assert response.content == knowledge_response.content
    assert response.answer_markdown == "**PTFE:** Temperaturhinweis aus kuratierter Evidenz."
    assert response.answer_trace is not None
    assert response.answer_trace["reply_source"] == "knowledge_service"
    assert response.answer_trace["answer_markdown_source"] == "knowledge_composer"
    assert response.answer_trace["composer_attempted"] is True
    assert response.answer_trace["composer_succeeded"] is True


@pytest.mark.asyncio
async def test_knowledge_answer_composer_failure_falls_back_to_deterministic_answer(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    _block_case_mutation(monkeypatch)

    async def fail_compose(*_args, **_kwargs):
        return KnowledgeAnswerComposerOutput(answer_markdown="", confidence_note=None)

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        fail_compose,
    )

    with caplog.at_level(logging.WARNING):
        response = await chat_endpoint(
            ChatRequest(message="Vergleich PTFE und FKM", session_id="composer-fallback"),
            current_user=_user(),
        )

    assert response.policy_path == "knowledge"
    assert response.answer_markdown == response.reply
    assert "knowledge answer composer failed" in caplog.text
    trace = _answer_trace(response)
    assert trace["reply_source"] == "knowledge_service"
    assert trace["answer_markdown_source"] == "composer_fallback"
    assert trace["composer_attempted"] is True
    assert trace["composer_succeeded"] is False
    assert trace["fallback_reason"] == "empty_answer_markdown"


@pytest.mark.asyncio
async def test_knowledge_answer_composer_retries_registry_default_when_configured_model_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = KnowledgeContextBuilder().build(
        user_message="Vergleiche NBR und PTFE",
        deterministic_answer="Deterministische Orientierung zu NBR und PTFE.",
    )

    class BadRequestError(Exception):
        pass

    class FakeCompletions:
        def __init__(self) -> None:
            self.models: list[str] = []

        async def create(self, **kwargs):
            self.models.append(str(kwargs["model"]))
            if len(self.models) == 1:
                raise BadRequestError("unsupported model")

            class Message:
                content = (
                    '{"answer_markdown":"**Kurzvergleich:** NBR und PTFE unterscheiden sich deutlich.",'
                    '"confidence_note":null}'
                )

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    completions = FakeCompletions()

    class FakeChat:
        pass

    FakeChat.completions = completions

    class FakeClient:
        pass

    FakeClient.chat = FakeChat()

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.get_async_llm",
        lambda _role: (FakeClient(), "gpt-5.4-nano"),
    )

    result = await KnowledgeAnswerComposer().compose(KnowledgeAnswerComposerInput(context=context))

    assert result.answer_markdown.startswith("**Kurzvergleich:**")
    assert completions.models == ["gpt-5.4-nano", "gpt-4o-mini"]


@pytest.mark.asyncio
async def test_material_comparison_answer_markdown_does_not_use_cockpit_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    _block_case_mutation(monkeypatch)

    async def compose(_self, _request: KnowledgeAnswerComposerInput):
        return KnowledgeAnswerComposerOutput(
            answer_markdown=(
                "Kurzvergleich: FKM und EPDM unterscheiden sich vor allem bei Medienprofil, "
                "Temperaturfenster und typischen Einsatzgrenzen. Das ist technische Orientierung, "
                "keine finale Materialfreigabe."
            ),
            confidence_note=None,
        )

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Vergleich FKM und EPDM fuer Dichtungen.", session_id="composer-material"),
        current_user=_user(),
    )

    assert "FKM" in str(response.answer_markdown)
    assert "EPDM" in str(response.answer_markdown)
    assert "Noch kein technischer Fall" not in str(response.answer_markdown)
    assert "Noch nicht moeglich" not in str(response.answer_markdown)
    assert "Starte, sobald" not in str(response.answer_markdown)
    assert response.proposed_case_delta is None


def test_pfas_prompt_requires_current_topic_limitation() -> None:
    context = KnowledgeContextBuilder().build(
        user_message="Was bedeutet PFAS fuer Dichtungen?",
        deterministic_answer="Kein kuratierter/RAG-Treffer.",
    )
    messages = build_knowledge_answer_composer_messages(
        KnowledgeAnswerComposerInput(context=context)
    )

    prompt_text = "\n".join(message["content"] for message in messages)
    assert "technical orientation" in prompt_text
    assert "not current legal advice" in prompt_text
    assert "No live regulatory source was retrieved" in prompt_text
    assert "regulatory_currentness_required" in prompt_text
