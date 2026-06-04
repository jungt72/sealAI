from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.communication.v7_contracts import (
    AnswerMode,
    AnswerPlan,
    CaseRelevance,
    ClaimLevel,
    FinalAnswerContract,
    FinalAnswerTrace,
    MutationPolicy,
    ResumeStrategy,
    ResumeTarget,
    RuntimeAction,
    RuntimeActionType,
    RuntimeAnswerBuilder,
    RouterSignals,
    SpeakableFact,
    StateAction,
    StateActionType,
    TaskFrame,
    TaskStack,
    TurnDecision,
    TurnKind,
    build_knowledge_override_runtime_action,
    build_rfq_readiness_runtime_action,
    build_runtime_action_from_turn_decision,
)


def test_turn_decision_supports_mixed_pending_slot_and_knowledge_turn() -> None:
    decision = TurnDecision(
        turn_kind=TurnKind.MIXED,
        primary_interpretation="pending_slot_answer_with_embedded_knowledge_question",
        router_signals=RouterSignals(
            nano_intent="knowledge_question",
            nano_confidence=0.81,
            deterministic_pending_slot_match=True,
            deterministic_value_extraction=True,
            active_case_exists=True,
        ),
        answer_mode=AnswerMode.PENDING_SLOT_ANSWER,
        mutation_policy=MutationPolicy.PROPOSED,
        state_actions=[
            StateAction(
                type=StateActionType.CANDIDATE_FACT,
                mutation_policy=MutationPolicy.PROPOSED,
                field="medium",
                value="Wasser mit Reinigerzusatz",
                requires_confirmation=True,
            )
        ],
        answer_obligations=[
            "acknowledge_candidate_fact",
            "answer_or_correct_material_assumption",
            "return_to_primary_task",
        ],
        case_relevance=CaseRelevance.ACTIVE_CASE_CONTEXT,
        resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER,
        resume_target_candidate=ResumeTarget(
            type="pending_question", target_field="medium"
        ),
        confidence=0.81,
    )

    dumped = decision.model_dump()
    assert dumped["state_actions"][0]["mutation_policy"] == "proposed"
    assert dumped["answer_mode"] == "pending_slot_answer"
    assert "assistant_message" not in dumped


def test_turn_decision_rejects_router_as_final_answer_voice() -> None:
    with pytest.raises(ValidationError):
        TurnDecision.model_validate(
            {
                "turn_kind": "knowledge",
                "primary_interpretation": "knowledge_question",
                "answer_mode": "no_case_knowledge",
                "mutation_policy": "forbidden",
                "assistant_message": "This field must not exist on the router decision.",
            }
        )


def test_side_question_cannot_default_to_validator_mutation() -> None:
    with pytest.raises(ValidationError):
        TurnDecision(
            turn_kind=TurnKind.ACTIVE_CASE_SIDE_QUESTION,
            primary_interpretation="side_question_shaft_surface",
            answer_mode=AnswerMode.ACTIVE_CASE_SIDE_QUESTION,
            mutation_policy=MutationPolicy.ALLOWED_BY_VALIDATOR,
        )


def test_task_stack_limits_side_task_depth_to_one() -> None:
    primary = TaskFrame(
        task_id="primary-1",
        type="governed_seal_design",
        phase="medium_intake",
        pending_question=ResumeTarget(type="pending_question", target_field="medium"),
    )
    side = TaskFrame(
        task_id="side-1",
        type="active_case_side_question",
        topic="shaft_surface_roughness",
        return_to=ResumeTarget(type="pending_question", target_field="medium"),
    )

    stack = TaskStack(primary_task=primary, active_side_task=side)
    assert stack.max_side_task_depth == 1

    with pytest.raises(ValidationError):
        TaskStack(primary_task=primary, active_side_task=side, max_side_task_depth=2)


def test_speakable_fact_requires_safe_phrase_and_bounds_candidate_claim() -> None:
    fact = SpeakableFact(
        fact_id="medium_chlor_candidate",
        field="medium",
        status="ambiguous",
        claim_level_max=ClaimLevel.L2_APPLICATION_ORIENTATION,
        structured_value={"value": "chlor", "needs_clarification": True},
        safe_phrases=[
            "Ich habe Chlor als Medium verstanden, aber die genaue Form ist noch offen."
        ],
        forbidden_phrases=["Chlor ist fuer den Werkstoff geeignet."],
        source="slot_binding",
    )

    assert fact.status == "ambiguous"
    assert fact.claim_level_max == ClaimLevel.L2_APPLICATION_ORIENTATION

    with pytest.raises(ValidationError):
        SpeakableFact(fact_id="bad", source="test")


def test_answer_plan_carries_resume_target_and_forbidden_claims() -> None:
    plan = AnswerPlan(
        answer_mode=AnswerMode.ACTIVE_CASE_SIDE_QUESTION,
        answer_goal="explain relevance and return to medium intake",
        response_obligations=[
            "answer_side_question_directly",
            "return_to_primary_task",
        ],
        resume_target=ResumeTarget(type="pending_question", target_field="medium"),
        allowed_claim_levels=[
            ClaimLevel.L1_GENERAL,
            ClaimLevel.L2_APPLICATION_ORIENTATION,
        ],
        forbidden_claims=["final_material_suitability", "rfq_ready"],
    )

    assert plan.resume_target is not None
    assert plan.resume_target.target_field == "medium"
    assert "rfq_ready" in plan.forbidden_claims


def test_runtime_action_maps_active_case_side_question_to_answer_then_resume() -> None:
    decision = TurnDecision(
        turn_kind=TurnKind.ACTIVE_CASE_SIDE_QUESTION,
        primary_interpretation="active_case_side_question",
        answer_mode=AnswerMode.ACTIVE_CASE_SIDE_QUESTION,
        mutation_policy=MutationPolicy.FORBIDDEN,
        resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER,
        resume_target_candidate=ResumeTarget(
            type="pending_question", target_field="medium"
        ),
    )

    action = build_runtime_action_from_turn_decision(decision)

    assert action.action_type == RuntimeActionType.ANSWER_THEN_RESUME
    assert action.answer_builder == RuntimeAnswerBuilder.ACTIVE_CASE_SIDE
    assert action.graph_allowed is False
    trace = action.as_trace()
    assert trace["runtime_action_built"] is True
    assert trace["runtime_action_type"] == "answer_then_resume"
    assert trace["graph_invocation_skipped_reason"] == (
        "active_case_side_question_answered_by_communication_runtime"
    )


def test_runtime_action_maps_pending_slot_answer_to_governed_graph_entry() -> None:
    decision = TurnDecision(
        turn_kind=TurnKind.PENDING_SLOT_ANSWER,
        primary_interpretation="pending_slot_answer",
        answer_mode=AnswerMode.PENDING_SLOT_ANSWER,
        mutation_policy=MutationPolicy.ALLOWED_BY_VALIDATOR,
        resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER,
    )

    action = build_runtime_action_from_turn_decision(decision)

    assert action.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH
    assert action.graph_allowed is True
    assert (
        action.graph_entry_reason == "pending_slot_answer_requires_governed_validation"
    )
    assert action.slot_candidate_detected is True


def test_runtime_action_maps_technical_case_challenge_to_governed_graph_entry() -> None:
    decision = TurnDecision(
        turn_kind=TurnKind.CASE_INTAKE,
        primary_interpretation="technical_case_challenge",
        answer_mode=AnswerMode.TECHNICAL_CASE_CHALLENGE,
        mutation_policy=MutationPolicy.PROPOSED,
        resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER,
    )

    action = build_runtime_action_from_turn_decision(decision)

    assert action.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH
    assert action.answer_mode == AnswerMode.TECHNICAL_CASE_CHALLENGE
    assert action.answer_builder == RuntimeAnswerBuilder.GOVERNED_OUTPUT_CONTRACT
    assert action.graph_allowed is True
    assert (
        action.graph_entry_reason == "technical_case_challenge_requires_governed_graph"
    )
    assert (
        action.next_runtime_action
        == "enter_governed_langgraph_for_technical_case_challenge"
    )


def test_runtime_action_rejects_graph_allowed_for_answer_only_actions() -> None:
    with pytest.raises(ValidationError):
        RuntimeAction(
            action_type=RuntimeActionType.ANSWER_ONLY,
            answer_mode=AnswerMode.ACTIVE_CASE_SIDE_QUESTION,
            mutation_policy=MutationPolicy.FORBIDDEN,
            graph_allowed=True,
            answer_builder=RuntimeAnswerBuilder.ACTIVE_CASE_SIDE,
            reason="invalid_contract",
        )


def test_knowledge_override_runtime_action_is_answer_only_and_traceable() -> None:
    action = build_knowledge_override_runtime_action(
        override_class="conversational_answer",
        active_case_exists=True,
    )

    assert action.action_type == RuntimeActionType.ANSWER_ONLY
    assert action.answer_builder == RuntimeAnswerBuilder.KNOWLEDGE_OVERRIDE
    assert action.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert action.graph_allowed is False
    trace = action.as_trace()
    assert trace["decision_source"] == "knowledge_override_classifier"
    assert trace["knowledge_override_class"] == "conversational_answer"
    assert (
        trace["graph_invocation_skipped_reason"]
        == "legacy_knowledge_override_answer_only"
    )


def test_rfq_readiness_runtime_action_is_answer_only_and_consent_bounded() -> None:
    action = build_rfq_readiness_runtime_action(
        rfq_action_type="show_readiness",
        action_type=RuntimeActionType.SHOW_RFQ_READINESS,
        reason="deterministic_rfq_readiness_question",
        trace={"rfq_ready": False, "rfq_known_missing_fields": ["Medium"]},
    )

    assert action.action_type == RuntimeActionType.SHOW_RFQ_READINESS
    assert action.answer_mode == AnswerMode.RFQ_READINESS
    assert action.answer_builder == RuntimeAnswerBuilder.RFQ_READINESS
    assert action.graph_allowed is False
    trace = action.as_trace()
    assert trace["rfq_intent_detected"] is True
    assert trace["rfq_action_type"] == "show_readiness"
    assert trace["consent_required"] is True
    assert trace["dispatch_allowed"] is False
    assert trace["external_contact_allowed"] is False
    assert trace["manufacturer_review_framing"] is True
    assert trace["final_approval_claim_allowed"] is False
    assert (
        trace["graph_invocation_skipped_reason"]
        == "rfq_readiness_answered_without_governed_graph"
    )


def test_final_answer_contract_keeps_reply_as_fallback_and_answer_markdown_visible() -> (
    None
):
    contract = FinalAnswerContract(
        reply="Deterministischer Fallback",
        answer_markdown="Natuerliche finale Antwort",
        answer_trace=FinalAnswerTrace(
            reply_source="governed_output_contract",
            answer_markdown_source="final_composer",
            answer_mode=AnswerMode.ACTIVE_CASE_SIDE_QUESTION,
            composer_tier="tier_b",
            composer_attempted=True,
            composer_succeeded=True,
        ),
    )

    assert contract.reply != contract.answer_markdown
    assert contract.answer_trace.final_visible_source == "answer_markdown"
    assert contract.answer_trace.composer_succeeded is True


def test_golden_conversation_doc_contains_required_v7_cases() -> None:
    root = Path(__file__).resolve().parents[4]
    doc = root / "docs" / "communication" / "golden_conversations_v7.md"
    text = doc.read_text(encoding="utf-8")

    required_ids = [
        "GC-01",
        "GC-02",
        "GC-03",
        "GC-04",
        "GC-05",
        "GC-06",
        "GC-07",
        "GC-08",
        "GC-09",
        "GC-10",
        "GC-11",
        "GC-12",
    ]
    for case_id in required_ids:
        assert case_id in text

    assert "expected answer_mode" in text
    assert "expected mutation_policy" in text
    assert "manual eval rubric" in text
