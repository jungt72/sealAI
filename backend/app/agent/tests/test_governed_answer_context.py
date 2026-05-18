from __future__ import annotations

import json

import pytest

from app.agent.communication.governed_answer_context import build_governed_answer_context
from app.agent.graph import output_contract_assembly as output_assembly
from app.agent.graph import GraphState
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.governance_node import governance_node
import app.agent.graph.nodes.intake_observe_node as intake_module
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.runtime.user_facing_reply import assemble_user_facing_reply
from app.agent.state.models import ConversationMessage, ObservedExtraction, PendingQuestion
from app.agent.v92.models import CalculationResult, CalculationState
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
    context = build_governed_answer_context(
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
            ConversationMessage(role="assistant", content="Formulierung ist fuer Slot-Bindung irrelevant."),
            ConversationMessage(role="user", content=message),
        ],
        user_turn_index=2 if pending_question else 1,
    )
    return await _assemble_output(await _run_governed_nodes(state))


@pytest.mark.asyncio
async def test_context_builder_includes_pending_question_from_output_strategy() -> None:
    state = await _run_turn("ich moechte mit dir eine dichtungsloesung erarbeiten")

    context = build_governed_answer_context(
        state,
        output_public=state.output_public,
        output_reply=state.output_reply,
        response_class=state.output_response_class,
        pending_question=state.pending_question,
    )

    assert context.pending_question is not None
    assert context.pending_question.target_field == "medium"
    assert context.pending_question.expected_answer_type == "medium_value"
    assert state.governed_answer_context["pending_question"]["target_field"] == "medium"


@pytest.mark.asyncio
async def test_context_builder_includes_current_slot_answer_binding() -> None:
    state = await _run_turn("chlor", pending_question=_pending_medium_question())
    context = build_governed_answer_context(
        state,
        output_public=state.output_public,
        output_reply=state.output_reply,
        response_class=state.output_response_class,
    )

    assert len(context.slot_answer_bindings) == 1
    binding = context.slot_answer_bindings[0]
    assert binding.target_field == "medium"
    assert binding.source == "pending_question"
    assert binding.raw_value == "chlor"


@pytest.mark.asyncio
async def test_context_marks_chlorine_ambiguity_without_suitability_approval() -> None:
    state = await _run_turn("chlor", pending_question=_pending_medium_question())
    context = build_governed_answer_context(
        state,
        output_public=state.output_public,
        output_reply=state.output_reply,
        response_class=state.output_response_class,
    )

    assert context.ambiguous_values
    ambiguous = context.ambiguous_values[0]
    assert ambiguous.field_key == "medium"
    assert ambiguous.normalized_value == "Chlor"
    assert ambiguous.clarification_question is not None
    assert "Chlorgas" in ambiguous.clarification_question
    assert "final_material_suitability" in context.forbidden_claims
    assert "do_not_approve_material_suitability" in context.safety_boundaries
    dumped = json.dumps(context.model_dump(mode="json"), ensure_ascii=False).casefold()
    assert "geeignet" not in dumped
    assert "freigegeben" not in dumped


@pytest.mark.asyncio
async def test_context_confirmed_facts_exclude_unvalidated_extraction_candidate() -> None:
    observed = GraphState().observed.with_extraction(
        ObservedExtraction(
            field_name="medium",
            raw_value="Chlor",
            source="llm",
            confidence=0.60,
            turn_index=1,
        )
    )
    state = GraphState(
        pending_message="chlor",
        observed=observed,
        conversation_messages=[ConversationMessage(role="user", content="chlor")],
        user_turn_index=1,
    )

    context = build_governed_answer_context(state)

    assert context.confirmed_facts == []
    assert context.accepted_updates == []


def test_context_builder_exposes_deterministic_calculation_results() -> None:
    state = GraphState(
        pending_message="Berechne die Umfangsgeschwindigkeit fuer 50 mm und 3000 rpm.",
        calculation=CalculationState(
            status="ready",
            results=[
                CalculationResult(
                    calculation_id="rwdr.surface_speed",
                    version="1.0",
                    calculator="surface_speed_from_rpm_and_diameter",
                    status="ok",
                    claim_level="L3_deterministic_calculation",
                    input_snapshot_hash="input-hash",
                    outputs={"v_surface_m_s": 7.854},
                    units={"v_surface_m_s": "m/s"},
                    output_snapshot_hash="output-hash",
                    validity_status="valid_for_screening",
                    limitations=["Screening-Zwischenwert, keine Freigabe."],
                )
            ],
        ),
    )

    context = build_governed_answer_context(state)

    assert len(context.calculation_results) == 1
    fact = context.calculation_results[0]
    assert fact.calculation_id == "rwdr.surface_speed"
    assert fact.label == "Umfangsgeschwindigkeit"
    assert fact.outputs["v_surface_m_s"] == pytest.approx(7.854)
    assert fact.units == {"v_surface_m_s": "m/s"}
    assert fact.claim_level == "L3_deterministic_calculation"
    assert fact.validity_status == "valid_for_screening"
    assert "keine Freigabe" in fact.limitation


def test_context_builder_excludes_stale_calculation_results_from_answer_context() -> None:
    state = GraphState(
        calculation=CalculationState(
            status="ready",
            results=[
                CalculationResult(
                    calculation_id="rwdr.surface_speed",
                    version="1.0",
                    calculator="surface_speed_from_rpm_and_diameter",
                    status="ok",
                    claim_level="L3_deterministic_calculation",
                    input_snapshot_hash="old-input",
                    outputs={"v_surface_m_s": 7.854},
                    units={"v_surface_m_s": "m/s"},
                    output_snapshot_hash="old-output",
                    validity_status="stale",
                )
            ],
        ),
    )

    context = build_governed_answer_context(state)

    assert context.calculation_results == []


@pytest.mark.asyncio
async def test_context_missing_fields_and_open_points_match_output_contract_source() -> None:
    state = await _run_turn("chlor", pending_question=_pending_medium_question())
    context = build_governed_answer_context(
        state,
        output_public=state.output_public,
        output_reply=state.output_reply,
        response_class=state.output_response_class,
    )

    assert context.missing_fields == state.output_public["missing_fields"]
    assert context.open_points == state.output_public["open_points"]
    assert "pressure_bar" in context.missing_fields
    assert "sealing_type" in context.missing_fields


@pytest.mark.asyncio
async def test_context_next_best_question_uses_chlorine_form_clarification() -> None:
    state = await _run_turn("chlor", pending_question=_pending_medium_question())
    context = build_governed_answer_context(
        state,
        output_public=state.output_public,
        output_reply=state.output_reply,
        response_class=state.output_response_class,
    )

    assert context.next_best_question is not None
    assert "Chlorgas" in context.next_best_question
    assert "Natriumhypochlorit" in context.next_best_question


@pytest.mark.asyncio
async def test_context_wiring_does_not_change_visible_reply_contract() -> None:
    state = await _run_turn("chlor", pending_question=_pending_medium_question())

    payload = assemble_user_facing_reply(
        reply=state.output_reply,
        structured_state=state.output_public,
        state_update=True,
        response_class=state.output_response_class,
        fallback_text=state.output_reply,
    )

    assert state.output_public["message"] == state.output_reply
    assert payload["reply"] == state.output_reply
    assert payload["answer_markdown"] == payload["reply"]
    assert state.governed_answer_context["answer_markdown_source"] == "not_composed_yet"


@pytest.mark.asyncio
async def test_context_serialization_contains_no_unsafe_payload_shapes() -> None:
    state = await _run_turn("chlor", pending_question=_pending_medium_question())
    raw = json.dumps(state.governed_answer_context, ensure_ascii=False).casefold()

    forbidden_fragments = [
        "embedding",
        "raw_document",
        "raw_rag",
        "stack trace",
        "traceback",
        "api_key",
        "secret",
    ]
    assert not any(fragment in raw for fragment in forbidden_fragments)


def test_context_patch_keeps_existing_route_boundaries() -> None:
    classifier = PreGateClassifier()

    assert classifier.classify(
        "Ich habe eine rotierende Welle mit 80 mm Durchmesser, 1500 rpm und Öl bei 90 Grad."
    ).classification == PreGateClassification.DOMAIN_INQUIRY
    assert classifier.classify("Was bedeutet PFAS für Dichtungen?").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Was ist bei Salzwasser und Dichtungen kritisch?").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Vergleiche FKM und EPDM für Dichtungen.").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Hallo, wie geht es dir?").classification == PreGateClassification.GREETING
