from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

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
    GovernedCalculationFact,
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


def test_contextual_fallback_adds_risk_orientation_before_slot_question() -> None:
    context = GovernedAnswerContext(
        latest_user_message=(
            "Ich habe einen RWDR: Welle 40 mm, 1450 rpm, Hydrauliköl HLP46, "
            "80 °C, etwa 0,5 bar an der Dichtstelle. Was ist technisch kritisch?"
        ),
        accepted_updates=[
            GovernedAnswerUpdate(
                field_key="speed_rpm",
                label="Drehzahl",
                value=1450,
                unit="rpm",
                source="user",
                status="accepted",
            )
        ],
        next_best_question="Meinst du mit 0,5 bar den Druck direkt an der Dichtung?",
        missing_fields=["pressure_bar"],
    )

    answer = render_governed_contextual_fallback(
        context,
        "Ich habe schon ein paar Eckdaten. Für den nächsten sinnvollen Schritt brauche ich noch eine präzise Angabe.",
    )

    assert "Technisch kritisch" in answer
    assert "Druck direkt an der Dichtlippe" in answer
    assert "Die wichtigste Rückfrage ist" in answer


def test_contextual_fallback_states_deterministic_calculation_before_question() -> None:
    context = GovernedAnswerContext(
        latest_user_message=(
            "Berechne mir bitte die Umfangsgeschwindigkeit fuer einen RWDR "
            "mit 50 mm Welle und 3000 rpm."
        ),
        calculation_results=[
            GovernedCalculationFact(
                calculation_id="rwdr.surface_speed",
                label="Umfangsgeschwindigkeit",
                outputs={"v_surface_m_s": 7.854},
                units={"v_surface_m_s": "m/s"},
                status="ok",
                claim_level="L3_deterministic_calculation",
                validity_status="valid_for_screening",
            )
        ],
        next_best_question="Welcher Druck liegt direkt an der Dichtstelle an?",
        missing_fields=["pressure_bar"],
    )

    answer = render_governed_contextual_fallback(
        context,
        "Welcher Druck liegt direkt an der Dichtstelle an?",
    )

    assert "Deterministisch berechnet" in answer
    assert "Umfangsgeschwindigkeit: 7,854 m/s" in answer
    assert "keine Freigabe" in answer
    assert "Welcher Druck liegt direkt an der Dichtstelle an?" in answer


def test_contextual_fallback_humanizes_first_leakage_intake_question() -> None:
    context = GovernedAnswerContext(
        latest_user_message=(
            "Hallo, ich habe eine Leckage an einer Pumpe und möchte die Dichtung "
            "sauber auslegen."
        ),
        next_best_question="Welches Medium soll abgedichtet werden?",
        missing_fields=["medium", "pressure_bar", "temperature_c"],
        response_class="structured_clarification",
    )

    assert composer_module.should_render_governed_contextual_fallback(
        context,
        "Welches Medium soll abgedichtet werden?",
    )

    answer = render_governed_contextual_fallback(
        context,
        "Welches Medium soll abgedichtet werden?",
    )

    assert "Leckage" in answer
    assert "Fallbild" in answer
    assert "Dafür muss ich zuerst wissen" in answer
    assert "Was kommt an der Dichtstelle genau an" in answer
    assert answer.strip() != "Welches Medium soll abgedichtet werden?"


def test_v91_guard_is_backward_compatible_when_context_field_is_missing() -> None:
    legacy_context = object()

    composer_module._validate_v91_final_answer(
        "Das ist eine technische Orientierung, keine Freigabe.",
        legacy_context,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_node_uses_composer_for_contextual_orientation_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        assert "Ursachencluster" in request.deterministic_reply
        return GovernedAnswerComposerOutput(
            answer_markdown=(
                "Bei früher Leckage an einem RWDR würde ich das Schadbild systematisch trennen. "
                "Welcher Öltyp liegt genau an?"
            ),
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)
    context = GovernedAnswerContext(
        latest_user_message="Ein Wellendichtring leckt nach zwei Wochen. Welche Ursachen würdest du systematisch prüfen?",
        accepted_updates=[
            GovernedAnswerUpdate(
                field_key="medium",
                label="Medium",
                value="Öl",
                source="user",
                status="accepted",
            )
        ],
        next_best_question="Welcher Öltyp liegt genau an?",
        missing_fields=["medium"],
        response_class="structured_clarification",
    )
    state = GraphState(
        output_reply="Danke, ich habe Öl als Medium verstanden. Welcher Öltyp liegt genau an?",
        governed_answer_context=context.model_dump(mode="json"),
    )

    result = await governed_answer_composer_node(state)

    assert result.output_answer_markdown_source == "governed_composer"
    assert "früher Leckage an einem RWDR" in result.output_answer_markdown
    assert "Welcher Öltyp" in result.output_answer_markdown


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


def test_contextual_answer_discipline_rejects_bare_medium_intake_question() -> None:
    context = GovernedAnswerContext(
        latest_user_message="Hallo, ich habe eine Leckage an einer Pumpe und möchte die Dichtung auslegen.",
        next_best_question="Welches Medium soll abgedichtet werden?",
        missing_fields=["medium"],
        response_class="structured_clarification",
    )

    with pytest.raises(GovernedAnswerComposerError, match="bare_medium_intake_question"):
        composer_module._validate_contextual_answer_discipline(
            (
                "Eine Leckage würde ich zuerst als Fallbild sauber eingrenzen.\n\n"
                "Dafür muss ich zuerst wissen: Welches Medium soll abgedichtet werden?"
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
    assert 'do not write the bare question "Welches Medium soll abgedichtet werden?"' in system_prompt


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
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "false")

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        pytest.fail("governed composer must not be called while disabled")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)
    state = await _run_turn("chlor", pending_question=_pending_medium_question())

    result = await governed_answer_composer_node(state)

    assert result.output_reply
    assert result.output_answer_markdown != result.output_reply
    assert result.output_answer_markdown_source == "composer_fallback"
    assert "Für die technische Einordnung" in result.output_answer_markdown
    assert result.governed_answer_composer_error == ""


@pytest.mark.asyncio
async def test_feature_flag_disabled_humanizes_first_leakage_intake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "false")

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        pytest.fail("governed composer must not be called while disabled")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)
    state = await _run_turn(
        "Hallo, ich habe eine Leckage an einer Pumpe und möchte die Dichtung sauber auslegen."
    )

    result = await governed_answer_composer_node(state)

    assert result.output_answer_markdown_source == "composer_fallback"
    assert "Leckage" in result.output_answer_markdown
    assert "Dafür muss ich zuerst wissen" in result.output_answer_markdown
    assert "Welches Medium soll abgedichtet werden?" not in result.output_answer_markdown
    assert result.output_answer_markdown != result.output_reply


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
async def test_stream_repairs_slot_only_material_answer_with_live_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = GovernedAnswerContext(
        latest_user_message=(
            "RWDR für Hydrauliköl HLP46 bei 80 °C. Ordne EPDM, FKM und NBR technisch ein."
        ),
        next_best_question="Welcher Druck liegt direkt an der Dichtstelle an?",
        response_class="structured_clarification",
    )
    first_answer = "Die wichtigste Rückfrage ist: Welcher Druck liegt direkt an der Dichtstelle an?"
    repaired_answer = (
        "EPDM ist bei HLP46 eher ein Warnpunkt; NBR und FKM bleiben Prüfhypothesen "
        "ohne Werkstofffreigabe.\n\n"
        "Die wichtigste Rückfrage ist: Welcher Druck liegt direkt an der Dichtstelle an?"
    )

    class FakeDelta:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeChoice:
        def __init__(self, content: str) -> None:
            self.delta = FakeDelta(content)

    class FakeChunk:
        def __init__(self, content: str) -> None:
            self.choices = [FakeChoice(content)]

    class FakeStream:
        def __init__(self, parts: list[str]) -> None:
            self.parts = parts

        def __aiter__(self):
            self._index = 0
            return self

        async def __anext__(self):
            if self._index >= len(self.parts):
                raise StopAsyncIteration
            value = self.parts[self._index]
            self._index += 1
            return FakeChunk(value)

    class FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs["stream"] is True
            return FakeStream([first_answer] if len(self.calls) == 1 else [repaired_answer])

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
        lambda _role: (FakeClient(), "gpt-4o-mini"),
    )

    events = [
        event
        async for event in GovernedAnswerComposer().stream(
            GovernedAnswerComposerInput(
                context=context,
                deterministic_reply="Welcher Druck liegt direkt an der Dichtstelle an?",
            )
        )
    ]

    assert [event.event_type for event in events] == ["chunk", "reset", "chunk", "final"]
    assert events[0].text == first_answer
    assert events[2].text == repaired_answer
    assert events[-1].output is not None
    assert events[-1].output.answer_markdown == repaired_answer
    assert len(completions.calls) == 2
    repair_payload = json.loads(completions.calls[1]["messages"][1]["content"])
    assert repair_payload["repair"]["reason"] == "missing_material_orientation"
    assert repair_payload["repair"]["must_mention_user_material_terms"] == ["EPDM", "FKM", "NBR"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["wasser", "öl", "salzwasser"])
async def test_composer_can_acknowledge_simple_medium_and_ask_next_question(
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        return GovernedAnswerComposerOutput(
            answer_markdown="Damit kann ich weiterarbeiten. Welche Temperatur sieht die Dichtstelle?",
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)
    state = await _run_turn(message, pending_question=_pending_medium_question())

    result = await governed_answer_composer_node(state)

    assert result.output_answer_markdown_source == "governed_composer"
    assert result.output_answer_markdown.startswith("Damit kann ich weiterarbeiten")
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

    assert payload["reply"] == state.output_answer_markdown
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


def test_assembly_polishes_visible_governed_markdown_before_payload() -> None:
    state = GraphState(
        output_reply="Deterministischer Fallback",
        output_response_class="structured_clarification",
        output_answer_markdown=(
            '"Die wichtigste Rueckfrage ist: Meinst du den Druckunterschied ueber der Dichtung?"'
        ),
        output_answer_markdown_source="governed_composer",
    )
    persisted = GovernedSessionState.model_validate(state.model_dump(mode="python"))
    context = _build_governed_reply_context(result_state=state, persisted_state=persisted)

    payload = _assemble_governed_stream_payload(context=context)

    assert payload["answer_markdown"] == (
        "Die wichtigste Rückfrage ist: Meinst du den Druckunterschied über der Dichtung?"
    )
    assert payload["assistant_message"] == payload["answer_markdown"]


@pytest.mark.asyncio
async def test_structured_clarification_output_contract_uses_composer_for_visible_wording(
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
    assert materialized.output_answer_markdown.startswith("Composer-Antwort")
    assert materialized.output_reply


@pytest.mark.asyncio
async def test_structured_clarification_composer_disabled_uses_contextual_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "false")

    async def fail_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        pytest.fail("governed composer must not run in full graph while disabled")

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fail_compose)

    _payload, materialized = await _run_structured_output_contract()

    assert materialized.output_reply
    assert materialized.output_answer_markdown != materialized.output_reply
    assert materialized.output_answer_markdown_source == "composer_fallback"
    assert "Dafür muss ich zuerst wissen" in materialized.output_answer_markdown
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

    assert materialized.output_answer_markdown
    assert materialized.output_answer_markdown_source == "composer_fallback"
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

    assert payload["reply"] == state.output_answer_markdown
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

    assert payload["reply"] == state.output_answer_markdown
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
