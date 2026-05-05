from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import app.agent.graph.nodes.intake_observe_node as intake_module
from app.agent.api.assembly import (
    _assemble_governed_stream_payload,
    _build_governed_reply_context,
)
from app.agent.api.utils import _materialize_governed_graph_result
from app.agent.communication import governed_answer_composer as composer_module
from app.agent.communication.governed_answer_composer import (
    GovernedAnswerComposer,
    GovernedAnswerComposerError,
    GovernedAnswerComposerInput,
    GovernedAnswerComposerOutput,
    parse_governed_answer_composer_output,
    render_governed_contextual_fallback,
)
from app.agent.communication.governed_answer_context import (
    GovernedAnswerContext,
    GovernedAnswerUpdate,
)
from app.agent.graph import GraphState
from app.agent.graph import output_contract_assembly as output_assembly
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.governance_node import governance_node
from app.agent.graph.nodes.governed_answer_composer_node import governed_answer_composer_node
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.runtime.clarification_priority import select_clarification_priority
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    ContextHintState,
    ConversationMessage,
    GovernedSessionState,
    PendingQuestion,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.services.pre_gate_classifier import PreGateClassifier


@pytest.fixture(autouse=True)
def _disable_llm_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake_module, "_ENABLE_LLM_EXTRACTION", False)


def _pending_medium_question() -> PendingQuestion:
    return PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text="Welches Medium soll abgedichtet werden?",
        asked_at_turn_id=1,
        source="governed_next_question",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        status="open",
    )


def _claim(field_name: str, value: object) -> AssertedClaim:
    return AssertedClaim(field_name=field_name, asserted_value=value)


async def _run_governed_nodes(state: GraphState) -> GraphState:
    for node in (
        intake_module.intake_observe_node,
        normalize_node,
        assert_node,
        governance_node,
    ):
        state = await node(state)
    return state


async def _assemble_output(state: GraphState) -> GraphState:
    response_class = output_assembly._determine_response_class(state)
    strategy = output_assembly.build_governed_conversation_strategy_contract(state, response_class)
    output_public = output_assembly._build_output_public_base(state, response_class)
    reply = await output_assembly._build_reply(state, response_class, strategy=strategy)
    output_public["message"] = reply
    pending_question = output_assembly._pending_question_from_strategy(
        state=state,
        response_class=response_class,
        strategy=strategy,
    )
    context = output_assembly.build_governed_answer_context(
        state,
        output_public=output_public,
        output_reply=reply,
        response_class=response_class,
        strategy=strategy,
        pending_question=pending_question,
    )
    return state.model_copy(
        update={
            "output_response_class": response_class,
            "output_public": output_public,
            "output_reply": reply,
            "pending_question": pending_question,
            "governed_answer_context": context.model_dump(mode="python"),
        }
    )


async def _run_turn(message: str, *, pending_question: PendingQuestion | None = None) -> GraphState:
    state = GraphState(
        pending_message=message,
        pending_question=pending_question,
        conversation_messages=[
            ConversationMessage(role="assistant", content="Die sichtbare Frage ist fuer Slot-Bindung nicht massgeblich."),
            ConversationMessage(role="user", content=message),
        ],
        user_turn_index=2 if pending_question else 1,
    )
    return await _assemble_output(await _run_governed_nodes(state))


def _truth_dump(state: GraphState) -> dict:
    return state.model_dump(
        mode="json",
        exclude={
            "output_answer_markdown",
            "output_answer_markdown_source",
            "governed_answer_composer_error",
        },
    )


def _interrupted_state(raw: object) -> GraphState:
    assert isinstance(raw, dict)
    assert "__interrupt__" in raw
    payload = list(raw["__interrupt__"])[0].value
    return GraphState.model_validate(payload["state"])


def test_contextual_fallback_asks_next_best_question_without_routine_confirmation() -> None:
    context = GovernedAnswerContext(
        accepted_updates=[
            GovernedAnswerUpdate(
                field_key="speed_rpm",
                label="Drehzahl",
                value=4000,
                unit="rpm",
                source="pending_question",
                status="accepted",
            )
        ],
        next_best_question="Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        missing_fields=["pressure_bar", "temperature_c", "installation"],
    )

    answer = render_governed_contextual_fallback(
        context,
        "Betriebsparameter erfasst: Drehzahl: 4000. Als naechstes brauche ich noch genau einen Kernwert.",
    )

    assert answer == "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?"
    assert "Danke" not in answer
    assert "4000" not in answer
    assert "bestaetig" not in answer.casefold()


def test_contextual_answer_discipline_rejects_routine_restatement() -> None:
    context = GovernedAnswerContext(
        accepted_updates=[
            GovernedAnswerUpdate(
                field_key="speed_rpm",
                label="Drehzahl",
                value=4000,
                unit="rpm",
                source="pending_question",
                status="accepted",
            ),
            GovernedAnswerUpdate(
                field_key="shaft_diameter_mm",
                label="Wellendurchmesser",
                value=80,
                unit="mm",
                source="pending_question",
                status="accepted",
            ),
        ],
        next_best_question="Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        missing_fields=["pressure_bar", "temperature_c"],
    )

    with pytest.raises(GovernedAnswerComposerError):
        composer_module._validate_contextual_answer_discipline(
            (
                "Die technischen Details sind klarer, und ich habe die Drehzahl von 4000 u/min "
                "sowie den Wellendurchmesser von 80 mm zur Kenntnis genommen. Wie hoch ist der Druck?"
            ),
            context,
        )


def test_rotary_context_with_speed_and_shaft_prioritizes_pressure_before_installation() -> None:
    state = GraphState(
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Salzwasser"),
                "sealing_type": _claim("sealing_type", "rwdr"),
                "speed_rpm": _claim("speed_rpm", 4000),
                "shaft_diameter_mm": _claim("shaft_diameter_mm", 80),
            },
            blocking_unknowns=[
                "pressure_bar",
                "temperature_c",
                "installation",
                "geometry_context",
            ],
        ),
        motion_hint=ContextHintState(label="rotary", confidence="high"),
        application_hint=ContextHintState(label="shaft_sealing", confidence="high"),
    )

    priority = select_clarification_priority(state, state.asserted.blocking_unknowns)

    assert priority is not None
    assert priority.focus_key == "pressure_bar"
    assert "druck" in priority.question.casefold()


def test_governed_answer_composer_prompt_requires_next_best_question_and_no_routine_thanks() -> None:
    system_prompt = Path(
        "backend/app/agent/prompts/governed/answer_composer.j2"
    ).read_text(encoding="utf-8")

    assert "next_best_question" in system_prompt
    assert "Do not ask the user to confirm a value they just supplied" in system_prompt
    assert "without thanking or repeating them routinely" in system_prompt


async def _run_structured_output_contract(
    message: str = "ich brauche hilfe bei einer dichtungslösung",
) -> tuple[dict, GraphState]:
    state = GraphState(
        pending_message=message,
        conversation_messages=[ConversationMessage(role="user", content=message)],
        user_turn_index=1,
    )
    state = await _run_governed_nodes(state)
    captured: dict[str, dict] = {}

    def fake_interrupt(payload: dict) -> None:
        captured["payload"] = payload
        return None

    with patch.object(output_assembly, "interrupt", fake_interrupt):
        result = await output_assembly.output_contract_node(state)

    assert isinstance(result, GraphState)
    return captured["payload"], result


@pytest.mark.asyncio
async def test_feature_flag_disabled_does_not_call_composer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", raising=False)

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        pytest.fail("governed composer must not be called while disabled")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)
    state = await _run_turn("chlor", pending_question=_pending_medium_question())

    result = await governed_answer_composer_node(state)

    assert result.output_reply
    assert result.output_answer_markdown == result.output_reply
    assert result.output_answer_markdown_source == "deterministic_reply"
    assert result.governed_answer_composer_error == ""


@pytest.mark.asyncio
async def test_composer_success_sets_answer_markdown_without_truth_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        assert request.context.ambiguous_values
        assert request.context.slot_answer_bindings[0].target_field == "medium"
        return GovernedAnswerComposerOutput(
            answer_markdown=(
                "Chlor ist als Medium im Arbeitsstand. Fuer die Auslegung muss ich die Form genauer einordnen: "
                "Geht es um Chlorgas, Chlorwasser, Natriumhypochlorit/Chlorbleichlauge oder ein chlorhaltiges "
                "Reinigungsmedium?"
            ),
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)
    state = await _run_turn("chlor", pending_question=_pending_medium_question())
    before_truth = _truth_dump(state)

    result = await governed_answer_composer_node(state)

    assert result.output_reply != result.output_answer_markdown
    assert result.output_answer_markdown_source == "governed_composer"
    assert "Chlor" in result.output_answer_markdown
    assert "Chlorgas" in result.output_answer_markdown
    assert "Medium angeben" not in result.output_answer_markdown
    assert "geeignet" not in result.output_answer_markdown.casefold()
    assert "freigegeben" not in result.output_answer_markdown.casefold()
    assert _truth_dump(result) == before_truth


@pytest.mark.asyncio
async def test_composer_failure_falls_back_without_secret_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        raise RuntimeError("OPENAI_API_KEY=secret-value")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)
    state = await _run_turn("chlor", pending_question=_pending_medium_question())

    result = await governed_answer_composer_node(state)

    assert result.output_answer_markdown != result.output_reply
    assert result.output_answer_markdown_source == "composer_fallback"
    assert "Chlor" in result.output_answer_markdown
    assert "Chlorgas" in result.output_answer_markdown
    assert "Medium angeben" not in result.output_answer_markdown
    assert result.governed_answer_composer_error == "RuntimeError"
    assert "secret" not in result.governed_answer_composer_error.casefold()
    assert "OPENAI_API_KEY" not in result.governed_answer_composer_error


@pytest.mark.asyncio
async def test_composer_retries_registry_default_when_configured_model_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _run_turn("chlor", pending_question=_pending_medium_question())
    context = composer_module.GovernedAnswerContext.model_validate(state.governed_answer_context)

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
                content = json.dumps(
                    {
                        "answer_markdown": "Chlor ist im Arbeitsstand. Geht es um Chlorgas oder Chlorwasser?",
                        "confidence_note": None,
                    }
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
        composer_module,
        "get_async_llm",
        lambda _role: (FakeClient(), "gpt-5.4-nano"),
    )

    result = await GovernedAnswerComposer().compose(
        GovernedAnswerComposerInput(context=context, deterministic_reply=state.output_reply)
    )

    assert result.answer_markdown.startswith("Chlor")
    assert completions.models == ["gpt-5.4-nano", "gpt-4o-mini"]


@pytest.mark.parametrize(
    "unsafe_answer",
    [
        "Die Lösung ist freigegeben.",
        "RFQ-ready.",
        "Material ist geeignet.",
        "Der Hersteller wird das akzeptieren.",
    ],
)
def test_parser_rejects_forbidden_approval_language(unsafe_answer: str) -> None:
    with pytest.raises(GovernedAnswerComposerError):
        parse_governed_answer_composer_output(
            json.dumps({"answer_markdown": unsafe_answer, "confidence_note": None})
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["wasser", "öl", "salzwasser"])
async def test_composer_can_acknowledge_simple_medium_and_ask_next_question(
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        supplied = request.context.accepted_updates[0].value
        assert supplied
        return GovernedAnswerComposerOutput(
            answer_markdown="In welchem Temperaturbereich arbeitet die Dichtstelle?",
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)
    state = await _run_turn(message, pending_question=_pending_medium_question())

    result = await governed_answer_composer_node(state)

    assert result.output_answer_markdown_source == "governed_composer"
    assert "Temperatur" in result.output_answer_markdown
    assert "Medium angeben" not in result.output_answer_markdown


@pytest.mark.asyncio
async def test_assembly_preserves_deterministic_reply_and_exposes_composer_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        return GovernedAnswerComposerOutput(
            answer_markdown="Chlor ist als Medium im Arbeitsstand. Um welche Chlorform geht es?",
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)
    state = await governed_answer_composer_node(
        await _run_turn("chlor", pending_question=_pending_medium_question())
    )
    persisted = GovernedSessionState.model_validate(state.model_dump(mode="python"))
    context = _build_governed_reply_context(result_state=state, persisted_state=persisted)

    payload = _assemble_governed_stream_payload(context=context, visible_reply=state.output_answer_markdown)

    assert payload["reply"] == state.output_reply
    assert payload["answer_markdown"] == state.output_answer_markdown
    assert payload["assistant_message"] == state.output_answer_markdown
    assert payload["run_meta"]["governed_answer_composer"]["source"] == "governed_composer"
    trace = payload["run_meta"]["answer_trace"]
    assert trace["reply_source"] == "governed_output_contract"
    assert trace["answer_markdown_source"] == "governed_composer"
    assert trace["final_visible_source"] == "answer_markdown"
    assert trace["composer_attempted"] is True
    assert trace["composer_succeeded"] is True
    assert trace["hcl_attempted"] is False
    assert trace["hcl_succeeded"] is False
    assert trace["fallback_reason"] is None
    assert trace["final_layer_source"] == "governed_composer"


def test_materialize_governed_graph_result_extracts_state_from_interrupt_payload() -> None:
    state = GraphState(
        output_reply="Deterministischer Fallback",
        output_answer_markdown="Komponierte Antwort",
        output_answer_markdown_source="governed_composer",
    )

    class FakeInterrupt:
        def __init__(self, value: dict) -> None:
            self.value = value

    raw = {"__interrupt__": (FakeInterrupt({"state": state.model_dump(mode="python")}),)}

    result = _materialize_governed_graph_result(raw)

    assert result.output_reply == "Deterministischer Fallback"
    assert result.output_answer_markdown == "Komponierte Antwort"
    assert result.output_answer_markdown_source == "governed_composer"


@pytest.mark.asyncio
async def test_structured_clarification_output_contract_reaches_composer_before_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")
    calls: list[str] = []

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        calls.append(request.context.response_class or "")
        return GovernedAnswerComposerOutput(
            answer_markdown="Composer-Antwort: Ich frage als Nächstes gezielt nach dem Medium.",
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)

    payload, materialized = await _run_structured_output_contract()
    interrupted = GraphState.model_validate(payload["state"])

    assert calls == ["structured_clarification"]
    assert interrupted.output_answer_markdown_source == "governed_composer"
    assert materialized.output_answer_markdown_source == "governed_composer"
    assert materialized.output_answer_markdown == "Composer-Antwort: Ich frage als Nächstes gezielt nach dem Medium."
    assert materialized.output_reply
    assert materialized.output_answer_markdown != materialized.output_reply


@pytest.mark.asyncio
async def test_structured_clarification_composer_disabled_preserves_deterministic_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", raising=False)

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        pytest.fail("governed composer must not run in full graph while disabled")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)

    _payload, materialized = await _run_structured_output_contract()

    assert materialized.output_reply
    assert materialized.output_answer_markdown == materialized.output_reply
    assert materialized.output_answer_markdown_source == "deterministic_reply"
    assert materialized.governed_answer_composer_error == ""


@pytest.mark.asyncio
async def test_structured_clarification_composer_failure_falls_back_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        raise RuntimeError("OPENAI_API_KEY=secret-value")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)

    _payload, materialized = await _run_structured_output_contract()

    assert materialized.output_answer_markdown != materialized.output_reply
    assert materialized.output_answer_markdown_source == "composer_fallback"
    assert "Welches Medium" in materialized.output_answer_markdown
    assert materialized.governed_answer_composer_error == "RuntimeError"
    assert "secret" not in materialized.governed_answer_composer_error.casefold()
    assert "OPENAI_API_KEY" not in materialized.governed_answer_composer_error


@pytest.mark.asyncio
async def test_structured_clarification_assembly_preserves_composed_markdown_from_interrupt_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        return GovernedAnswerComposerOutput(
            answer_markdown="Composer-Antwort: Bitte beschreibe kurz das Medium an der Dichtstelle.",
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)

    _payload, state = await _run_structured_output_contract()
    persisted = GovernedSessionState.model_validate(state.model_dump(mode="python"))
    context = _build_governed_reply_context(result_state=state, persisted_state=persisted)

    payload = _assemble_governed_stream_payload(context=context, visible_reply=state.output_answer_markdown)

    assert payload["reply"] == state.output_reply
    assert payload["answer_markdown"] == state.output_answer_markdown
    assert payload["assistant_message"] == state.output_answer_markdown
    assert payload["run_meta"]["governed_answer_composer"]["source"] == "governed_composer"
    assert payload["run_meta"]["answer_trace"]["reply_source"] == "governed_output_contract"
    assert payload["run_meta"]["answer_trace"]["answer_markdown_source"] == "governed_composer"
    assert payload["run_meta"]["answer_trace"]["composer_attempted"] is True
    assert payload["run_meta"]["answer_trace"]["composer_succeeded"] is True


@pytest.mark.asyncio
async def test_assembly_traces_governed_composer_fallback_without_leaking_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        raise RuntimeError("OPENAI_API_KEY=secret-value")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)
    state = await governed_answer_composer_node(
        await _run_turn("chlor", pending_question=_pending_medium_question())
    )
    persisted = GovernedSessionState.model_validate(state.model_dump(mode="python"))
    context = _build_governed_reply_context(result_state=state, persisted_state=persisted)

    payload = _assemble_governed_stream_payload(context=context, visible_reply=state.output_reply)

    assert payload["reply"] == state.output_reply
    assert payload["answer_markdown"] == state.output_answer_markdown
    assert payload["answer_markdown"] != state.output_reply
    trace = payload["run_meta"]["answer_trace"]
    assert trace["reply_source"] == "governed_output_contract"
    assert trace["answer_markdown_source"] == "composer_fallback"
    assert trace["composer_attempted"] is True
    assert trace["composer_succeeded"] is False
    assert trace["fallback_reason"] == "RuntimeError"
    assert trace["final_layer_source"] == "composer_fallback"
    dumped = json.dumps(trace, ensure_ascii=True)
    assert "secret" not in dumped.casefold()
    assert "OPENAI_API_KEY" not in dumped


def test_assembly_ignores_legacy_visible_reply_when_no_governed_composer_runs() -> None:
    state = GraphState(
        output_reply="Bitte Medium angeben.",
        output_response_class="structured_clarification",
    )
    persisted = GovernedSessionState()
    context = _build_governed_reply_context(result_state=state, persisted_state=persisted)

    payload = _assemble_governed_stream_payload(
        context=context,
        visible_reply="Welches Medium soll abgedichtet werden?",
        visible_reply_trace={
            "reply_source": "hcl",
            "answer_markdown_source": "hcl",
            "final_visible_source": "answer_markdown",
            "composer_attempted": False,
            "composer_succeeded": False,
            "hcl_attempted": True,
            "hcl_succeeded": True,
            "fallback_reason": None,
        },
    )

    trace = payload["run_meta"]["answer_trace"]
    assert payload["reply"] == "Bitte Medium angeben."
    assert payload["answer_markdown"] == payload["reply"]
    assert payload["assistant_message"] == "Bitte Medium angeben."
    assert trace["reply_source"] == "governed_output_contract"
    assert trace["answer_markdown_source"] == "deterministic_fallback"
    assert trace["hcl_attempted"] is False
    assert trace["hcl_succeeded"] is False
    assert trace["final_layer_source"] == "deterministic_fallback"


def test_existing_non_governed_routes_do_not_require_governed_composer() -> None:
    classifier = PreGateClassifier()

    assert classifier.classify("Was bedeutet PFAS für Dichtungen?").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Vergleiche FKM und EPDM für Dichtungen.").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Hallo, wie geht es dir?").classification == PreGateClassification.GREETING
    assert classifier.classify(
        "Ich habe eine rotierende Welle mit 80 mm Durchmesser, 1500 rpm und Öl bei 90 Grad."
    ).classification == PreGateClassification.DOMAIN_INQUIRY
