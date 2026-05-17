from __future__ import annotations

import logging

import pytest

from app.agent.api.models import ChatRequest
from app.agent.api.dispatch import _compose_knowledge_answer_if_enabled
from app.agent.api.routes.chat import chat_endpoint
from app.agent.communication.answer_composer import (
    KnowledgeAnswerComposer,
    KnowledgeAnswerComposerError,
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


def test_knowledge_service_answers_epdm_hlp46_without_case_slot_question() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_research_fallback_enabled=False,
    ).answer("Ist EPDM für Hydrauliköl HLP46 bei 80 °C und 10 bar geeignet? Keine Freigabe, nur Einordnung.")

    assert "EPDM" in response.content
    assert "HLP46" in response.content
    assert "mineralöl" in response.content.casefold()
    assert "keine Freigabe" in response.content
    assert "Meinst du mit 10 bar" not in response.content


def test_knowledge_service_uses_deterministic_hot_water_risk_comparison() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_research_fallback_enabled=False,
    ).answer("Vergleiche PTFE, FKM und EPDM für Heißwasser bei 120 °C. Wo liegen die typischen Risiken?")

    assert "PTFE" in response.content
    assert "FKM" in response.content
    assert "EPDM" in response.content
    assert "Heißwasser" in response.content
    assert "Evidenzkontext" not in response.content
    assert "vorlaeufige" not in response.content


@pytest.mark.parametrize("material", ["FFKM", "NBR", "PTFE"])
def test_knowledge_service_answers_single_material_from_profile(material: str) -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_research_fallback_enabled=False,
    ).answer(f"bitte gebe mir detaillierte informationen zu {material}")

    assert material in response.content
    assert "Welches Medium soll abgedichtet werden" not in response.content
    assert "keine Freigabe" in response.content
    assert response.answer_trace is None
    assert response.knowledge_answer_view.knowledge_evidence
    assert response.knowledge_answer_view.knowledge_evidence[0].note == (
        f"system_derived_material_definition:{material}"
    )


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
async def test_simple_material_definition_answer_is_compacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = KnowledgeContextBuilder().build(
        user_message="Was ist NBR? Bitte antworte kurz und professionell.",
        deterministic_answer=(
            "NBR steht für Acrylnitril-Butadien-Kautschuk, häufig auch "
            "Nitrilkautschuk genannt. In der Dichtungstechnik ist NBR ein "
            "verbreiteter Elastomerwerkstoff. Typische Orientierung: "
            "- NBR wird oft im Umfeld von mineralölbasierten Medien betrachtet. "
            "- Kritisch können Ozon, UV, Witterung und manche Lösemittel sein. "
            "- Das Verhalten hängt stark von Rezeptur und Temperatur ab. "
            "Bis dahin ist das technische Orientierung, keine Freigabe."
        ),
    )

    class FakeCompletions:
        async def create(self, **_kwargs):
            class Message:
                content = (
                    '{"answer_markdown":"### NBR (Acrylnitril-Butadien-Kautschuk)\\n\\n'
                    'NBR ist ein Elastomerwerkstoff.\\n\\n'
                    '### Typische Eigenschaften und Anwendungen\\n\\n'
                    '- Medienverträglichkeit: mineralölbasierte Medien.\\n'
                    '- Kritische Einflüsse: Ozon und UV.\\n\\n'
                    '### Limitierungen/Annahmen\\n\\n'
                    'Diese Informationen dienen nur der technischen Orientierung.\\n\\n'
                    '### Nächste Frage\\n\\n'
                    'Welche Anwendung liegt vor?",'
                    '"confidence_note":null}'
                )

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.get_async_llm",
        lambda _role: (FakeClient(), "gpt-4o-mini"),
    )

    result = await KnowledgeAnswerComposer().compose(KnowledgeAnswerComposerInput(context=context))

    assert result.answer_markdown.startswith("NBR steht für Acrylnitril")
    assert "Limitierungen/Annahmen" not in result.answer_markdown
    assert "Nächste Frage" not in result.answer_markdown
    assert "Caveat" not in result.answer_markdown
    assert "Das Verhalten hängt stark" not in result.answer_markdown
    assert "keine technische Freigabe" in result.answer_markdown
    assert len(result.answer_markdown) < 800


@pytest.mark.asyncio
async def test_simple_definition_compaction_respects_requested_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = KnowledgeContextBuilder().build(
        user_message="Was ist FFKM?",
        deterministic_answer=(
            "NBR steht für Acrylnitril-Butadien-Kautschuk. Typische Orientierung: "
            "- NBR wird oft im Umfeld von mineralölbasierten Medien betrachtet. "
            "Das ist technische Orientierung, keine technische Freigabe."
        ),
    )

    class FakeCompletions:
        async def create(self, **_kwargs):
            class Message:
                content = (
                    '{"answer_markdown":"FFKM ist ein Perfluorelastomer. Das ist technische '
                    'Orientierung, keine Freigabe.",'
                    '"confidence_note":null}'
                )

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.get_async_llm",
        lambda _role: (FakeClient(), "gpt-4o-mini"),
    )

    result = await KnowledgeAnswerComposer().compose(KnowledgeAnswerComposerInput(context=context))

    assert result.answer_markdown.startswith("FFKM ist")
    assert "Acrylnitril" not in result.answer_markdown


@pytest.mark.asyncio
async def test_composer_rejects_material_subject_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = KnowledgeContextBuilder().build(
        user_message="bitte gebe mir detaillierte informationen zu FFKM",
        deterministic_answer=KnowledgeService(
            factcard_store=_FactcardStore([]),
            llm_research_fallback_enabled=False,
        ).answer("bitte gebe mir detaillierte informationen zu FFKM").content,
        recent_history=(
            KnowledgeConversationTurn(
                role="user",
                content="bitte gebe mir detaillierte infos zu NBR",
            ),
            KnowledgeConversationTurn(
                role="assistant",
                content="NBR steht für Acrylnitril-Butadien-Kautschuk.",
            ),
        ),
    )

    class FakeCompletions:
        async def create(self, **_kwargs):
            class Message:
                content = (
                    '{"answer_markdown":"NBR steht für Acrylnitril-Butadien-Kautschuk. '
                    'Das ist technische Orientierung, keine Freigabe.",'
                    '"confidence_note":null}'
                )

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.get_async_llm",
        lambda _role: (FakeClient(), "gpt-4o-mini"),
    )

    with pytest.raises(KnowledgeAnswerComposerError, match="requested_subject"):
        await KnowledgeAnswerComposer().compose(KnowledgeAnswerComposerInput(context=context))


@pytest.mark.asyncio
async def test_composer_rejects_unscoped_material_suitability_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = KnowledgeContextBuilder().build(
        user_message="bitte gebe mir detaillierte informationen zu NBR",
        deterministic_answer=KnowledgeService(
            factcard_store=_FactcardStore([]),
            llm_research_fallback_enabled=False,
        ).answer("bitte gebe mir detaillierte informationen zu NBR").content,
    )

    class FakeCompletions:
        async def create(self, **_kwargs):
            class Message:
                content = (
                    '{"answer_markdown":"NBR ist für viele ölnahe Dichtstellen geeignet ist, '
                    'wenn das Medium passt. Das ist technische Orientierung.",'
                    '"confidence_note":null}'
                )

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.get_async_llm",
        lambda _role: (FakeClient(), "gpt-4o-mini"),
    )

    with pytest.raises(KnowledgeAnswerComposerError, match="unsafe_material_suitability"):
        await KnowledgeAnswerComposer().compose(KnowledgeAnswerComposerInput(context=context))


@pytest.mark.asyncio
async def test_composer_rejects_unscoped_eignung_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = KnowledgeContextBuilder().build(
        user_message="bitte gebe mir detaillierte informationen zu NBR",
        deterministic_answer=KnowledgeService(
            factcard_store=_FactcardStore([]),
            llm_research_fallback_enabled=False,
        ).answer("bitte gebe mir detaillierte informationen zu NBR").content,
    )

    class FakeCompletions:
        async def create(self, **_kwargs):
            class Message:
                content = (
                    '{"answer_markdown":"### NBR\\n\\n- **Gute Eignung für**: '
                    'Mineralöle und Fette. Das ist technische Orientierung.",'
                    '"confidence_note":null}'
                )

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.get_async_llm",
        lambda _role: (FakeClient(), "gpt-4o-mini"),
    )

    with pytest.raises(KnowledgeAnswerComposerError, match="unsafe_material_suitability_label"):
        await KnowledgeAnswerComposer().compose(KnowledgeAnswerComposerInput(context=context))


@pytest.mark.asyncio
async def test_composer_repairs_unsafe_material_wording_with_second_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = KnowledgeContextBuilder().build(
        user_message="bitte gebe mir detaillierte informationen zu NBR",
        deterministic_answer=KnowledgeService(
            factcard_store=_FactcardStore([]),
            llm_research_fallback_enabled=False,
        ).answer("bitte gebe mir detaillierte informationen zu NBR").content,
    )

    class FakeCompletions:
        def __init__(self) -> None:
            self.calls = 0
            self.repair_payload_seen = False

        async def create(self, **kwargs):
            self.calls += 1
            payload = str(kwargs["messages"][-1]["content"])
            if "repair_instruction" in payload:
                self.repair_payload_seen = True

            class Message:
                content = (
                    '{"answer_markdown":"NBR ist gut geeignet für Mineralöle.",'
                    '"confidence_note":null}'
                )

            if self.calls > 1:
                Message.content = (
                    '{"answer_markdown":"NBR wird bei Mineralölen und Schmierfetten häufig '
                    'als naheliegende Prüfrichtung betrachtet. Das bleibt technische '
                    'Orientierung, keine Freigabe.",'
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
        lambda _role: (FakeClient(), "gpt-4o-mini"),
    )

    result = await KnowledgeAnswerComposer().compose(KnowledgeAnswerComposerInput(context=context))

    assert completions.calls == 2
    assert completions.repair_payload_seen is True
    assert "gut geeignet" not in result.answer_markdown
    assert "naheliegende Prüfrichtung" in result.answer_markdown


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


def test_composer_prompt_carries_requested_subject_contract() -> None:
    context = KnowledgeContextBuilder().build(
        user_message="Was ist FFKM?",
        deterministic_answer="FFKM ist ein Perfluorelastomer.",
        recent_history=(
            KnowledgeConversationTurn(role="user", content="Was ist NBR?"),
            KnowledgeConversationTurn(role="assistant", content="NBR steht für ..."),
        ),
    )
    messages = build_knowledge_answer_composer_messages(
        KnowledgeAnswerComposerInput(context=context)
    )

    prompt_text = "\n".join(message["content"] for message in messages)
    assert '"requested_subjects": ["FFKM"]' in prompt_text
    assert "latest user message is authoritative" in prompt_text
