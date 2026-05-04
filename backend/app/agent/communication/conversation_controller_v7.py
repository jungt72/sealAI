from __future__ import annotations

from dataclasses import dataclass

from app.agent.communication.v7_contracts import (
    AnswerMode,
    CaseRelevance,
    MutationPolicy,
    ResumeStrategy,
    ResumeTarget,
    RouterSignals,
    StateAction,
    StateActionType,
    TaskFrame,
    TaskStack,
    TurnDecision,
    TurnKind,
)
from app.agent.state.models import PendingQuestion, SlotAnswerBinding
from app.domain.pre_gate_classification import PreGateClassification


@dataclass(frozen=True, slots=True)
class ConversationControllerInput:
    user_message: str
    pre_gate_classification: PreGateClassification
    pre_gate_confidence: float = 0.5
    pre_gate_reason: str = ""
    active_case_exists: bool = False
    pending_question: PendingQuestion | None = None
    slot_answer_binding: SlotAnswerBinding | None = None


class ConversationControllerV7:
    """V7.1 turn decision adapter.

    This is the first central seam for replacing scattered routing decisions.
    It is intentionally deterministic for Patch 0/1: future nano-router output
    should be added as RouterSignals, not as an independent final voice.
    """

    def decide(self, payload: ConversationControllerInput) -> TurnDecision:
        if payload.slot_answer_binding is not None:
            return self._pending_slot_answer(payload)
        if self._looks_like_process_question(payload.user_message):
            if payload.active_case_exists:
                return self._active_case_process_question(payload)
            return self._meta(payload)
        if payload.active_case_exists and self._looks_like_side_question(payload.user_message):
            return self._knowledge_or_side_question(payload)
        if payload.pre_gate_classification in {PreGateClassification.KNOWLEDGE_QUERY, PreGateClassification.DEEP_DIVE}:
            return self._knowledge_or_side_question(payload)
        if payload.pre_gate_classification is PreGateClassification.GREETING:
            return self._smalltalk(payload)
        if payload.pre_gate_classification is PreGateClassification.META_QUESTION:
            return self._meta(payload)
        if payload.pre_gate_classification is PreGateClassification.BLOCKED:
            return self._blocked(payload)
        return self._governed_intake(payload)

    def _looks_like_process_question(self, message: str) -> bool:
        normalized = " ".join((message or "").casefold().split())
        if not normalized:
            return False
        return any(
            phrase in normalized
            for phrase in (
                "wie kannst du mir",
                "wie kannst du helfen",
                "wie hilfst du mir",
                "was kannst du fuer mich tun",
                "was kannst du für mich tun",
                "was kannst du tun",
                "was machst du jetzt",
                "was machst du genau",
                "wie laeuft die analyse",
                "wie läuft die analyse",
                "wie funktioniert die analyse",
                "welche informationen brauchst",
                "was brauchst du von mir",
                "warum fragst",
                "warum brauchst",
                "wozu fragst",
                "wozu brauchst",
                "weshalb fragst",
                "weshalb brauchst",
            )
        )

    def _looks_like_side_question(self, message: str) -> bool:
        normalized = " ".join((message or "").casefold().split())
        if not normalized:
            return False
        if any(
            phrase in normalized
            for phrase in (
                "was bedeutet",
                "was heisst",
                "was heißt",
                "was ist der unterschied",
                "unterschied zwischen",
                "welche rolle spielt",
                "warum ist das wichtig",
                "warum ist der druck wichtig",
                "warum ist die temperatur wichtig",
                "warum ist das medium wichtig",
                "wie ist es mit",
                "wie sieht es mit",
                "was ist mit",
            )
        ):
            return True
        material_tokens = ("fkm", "nbr", "epdm", "ptfe", "ffkm", "vmq", "hnbr")
        if normalized.startswith("und ") and any(token in normalized for token in material_tokens):
            return True
        return False

    def _router_signals(self, payload: ConversationControllerInput) -> RouterSignals:
        return RouterSignals(
            nano_intent=payload.pre_gate_classification.value.lower(),
            nano_confidence=payload.pre_gate_confidence,
            deterministic_pending_slot_match=payload.slot_answer_binding is not None,
            deterministic_value_extraction=payload.slot_answer_binding is not None,
            active_case_exists=payload.active_case_exists,
        )

    def _task_stack(self, payload: ConversationControllerInput, *, side_topic: str | None = None) -> TaskStack | None:
        if not payload.active_case_exists and payload.pending_question is None:
            return None
        pending = None
        if payload.pending_question is not None:
            pending = ResumeTarget(
                type="pending_question",
                target_field=payload.pending_question.target_field,
                question_text=payload.pending_question.question_text,
            )
        primary = TaskFrame(
            task_id="primary",
            type="governed_seal_design",
            phase=(payload.pending_question.target_field if payload.pending_question else "unknown"),
            pending_question=pending,
        )
        side = None
        if side_topic:
            side = TaskFrame(
                task_id="side",
                type="active_case_side_question",
                topic=side_topic,
                return_to=pending,
            )
        return TaskStack(primary_task=primary, active_side_task=side)

    def _pending_slot_answer(self, payload: ConversationControllerInput) -> TurnDecision:
        binding = payload.slot_answer_binding
        assert binding is not None
        mutation_policy = MutationPolicy.PROPOSED if binding.needs_clarification else MutationPolicy.ALLOWED_BY_VALIDATOR
        return TurnDecision(
            turn_kind=TurnKind.PENDING_SLOT_ANSWER,
            primary_interpretation="pending_slot_answer",
            router_signals=self._router_signals(payload),
            answer_mode=AnswerMode.PENDING_SLOT_ANSWER,
            mutation_policy=mutation_policy,
            state_actions=[
                StateAction(
                    type=StateActionType.CANDIDATE_FACT,
                    mutation_policy=mutation_policy,
                    field=binding.target_field,
                    value=binding.normalized_value if binding.normalized_value is not None else binding.raw_value,
                    source="pending_question",
                    requires_confirmation=binding.needs_clarification,
                    needs_clarification=binding.needs_clarification,
                    reason="bound_from_structured_pending_question",
                )
            ],
            answer_obligations=[
                "acknowledge_candidate_fact",
                "clarify_ambiguous_value" if binding.needs_clarification else "ask_next_best_question",
                "do_not_claim_material_suitability",
                "return_to_primary_task",
            ],
            case_relevance=CaseRelevance.ACTIVE_CASE_CONTEXT,
            resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER,
            resume_target_candidate=ResumeTarget(type="pending_question", target_field=binding.target_field),
            task_stack=self._task_stack(payload),
            confidence=max(payload.pre_gate_confidence, binding.confidence),
        )

    def _knowledge_or_side_question(self, payload: ConversationControllerInput) -> TurnDecision:
        if payload.active_case_exists:
            pending_target = None
            if payload.pending_question is not None:
                pending_target = ResumeTarget(
                    type="pending_question",
                    target_field=payload.pending_question.target_field,
                    question_text=payload.pending_question.question_text,
                )
            return TurnDecision(
                turn_kind=TurnKind.ACTIVE_CASE_SIDE_QUESTION,
                primary_interpretation="active_case_side_question",
                router_signals=self._router_signals(payload),
                answer_mode=AnswerMode.ACTIVE_CASE_SIDE_QUESTION,
                mutation_policy=MutationPolicy.FORBIDDEN,
                answer_obligations=["answer_side_question_directly", "connect_to_active_case", "return_to_primary_task"],
                case_relevance=CaseRelevance.ACTIVE_CASE_CONTEXT,
                resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER if pending_target else ResumeStrategy.NONE,
                resume_target_candidate=pending_target,
                task_stack=self._task_stack(payload, side_topic="knowledge_side_question"),
                confidence=payload.pre_gate_confidence,
            )
        return TurnDecision(
            turn_kind=TurnKind.KNOWLEDGE,
            primary_interpretation="no_case_knowledge",
            router_signals=self._router_signals(payload),
            answer_mode=AnswerMode.MATERIAL_COMPARISON
            if "vergleich" in payload.pre_gate_reason or "material" in payload.pre_gate_reason
            else AnswerMode.NO_CASE_KNOWLEDGE,
            mutation_policy=MutationPolicy.FORBIDDEN,
            answer_obligations=["answer_user_question", "do_not_create_case"],
            case_relevance=CaseRelevance.NO_CASE,
            resume_strategy=ResumeStrategy.NONE,
            confidence=payload.pre_gate_confidence,
        )

    def _active_case_process_question(self, payload: ConversationControllerInput) -> TurnDecision:
        pending_target = None
        if payload.pending_question is not None:
            pending_target = ResumeTarget(
                type="pending_question",
                target_field=payload.pending_question.target_field,
                question_text=payload.pending_question.question_text,
            )
        return TurnDecision(
            turn_kind=TurnKind.META,
            primary_interpretation="active_case_process_question",
            router_signals=self._router_signals(payload),
            answer_mode=AnswerMode.ACTIVE_CASE_PROCESS_QUESTION,
            mutation_policy=MutationPolicy.FORBIDDEN,
            answer_obligations=[
                "answer_latest_user_question_first",
                "use_active_case_context",
                "explain_current_state_briefly",
                "return_to_pending_question_if_still_valid",
                "ask_at_most_one_question",
                "do_not_mutate_case_state",
            ],
            case_relevance=CaseRelevance.ACTIVE_CASE_CONTEXT,
            resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER if pending_target else ResumeStrategy.NONE,
            resume_target_candidate=pending_target,
            task_stack=self._task_stack(payload, side_topic="process_question"),
            confidence=max(payload.pre_gate_confidence, 0.82),
        )

    def _smalltalk(self, payload: ConversationControllerInput) -> TurnDecision:
        return TurnDecision(
            turn_kind=TurnKind.SMALLTALK,
            primary_interpretation="smalltalk",
            router_signals=self._router_signals(payload),
            answer_mode=AnswerMode.SMALLTALK,
            mutation_policy=MutationPolicy.FORBIDDEN,
            answer_obligations=["respond_briefly", "do_not_mutate_case"],
            case_relevance=CaseRelevance.ACTIVE_CASE_CONTEXT if payload.active_case_exists else CaseRelevance.NO_CASE,
            resume_strategy=ResumeStrategy.NONE,
            task_stack=self._task_stack(payload),
            confidence=payload.pre_gate_confidence,
        )

    def _meta(self, payload: ConversationControllerInput) -> TurnDecision:
        pending_target = None
        if payload.pending_question is not None:
            pending_target = ResumeTarget(
                type="pending_question",
                target_field=payload.pending_question.target_field,
                question_text=payload.pending_question.question_text,
            )
        return TurnDecision(
            turn_kind=TurnKind.META,
            primary_interpretation="meta_or_process_question",
            router_signals=self._router_signals(payload),
            answer_mode=AnswerMode.META_QUESTION,
            mutation_policy=MutationPolicy.FORBIDDEN,
            answer_obligations=["answer_process_question", "return_to_primary_task"],
            case_relevance=CaseRelevance.ACTIVE_CASE_CONTEXT if payload.active_case_exists else CaseRelevance.NO_CASE,
            resume_strategy=ResumeStrategy.RESTORE_TO_PENDING_QUESTION_V1 if pending_target else ResumeStrategy.NONE,
            resume_target_candidate=pending_target,
            task_stack=self._task_stack(payload),
            confidence=payload.pre_gate_confidence,
        )

    def _blocked(self, payload: ConversationControllerInput) -> TurnDecision:
        return TurnDecision(
            turn_kind=TurnKind.UNSAFE,
            primary_interpretation="blocked_or_unsupported",
            router_signals=RouterSignals(
                nano_intent=payload.pre_gate_classification.value.lower(),
                nano_confidence=payload.pre_gate_confidence,
                active_case_exists=payload.active_case_exists,
                safety_blocked=True,
            ),
            answer_mode=AnswerMode.SAFETY_BLOCKED,
            mutation_policy=MutationPolicy.FORBIDDEN,
            answer_obligations=["explain_boundary"],
            case_relevance=CaseRelevance.UNKNOWN,
            resume_strategy=ResumeStrategy.NONE,
            confidence=payload.pre_gate_confidence,
        )

    def _governed_intake(self, payload: ConversationControllerInput) -> TurnDecision:
        return TurnDecision(
            turn_kind=TurnKind.CASE_INTAKE,
            primary_interpretation="governed_case_intake",
            router_signals=self._router_signals(payload),
            answer_mode=AnswerMode.GOVERNED_INTAKE,
            mutation_policy=MutationPolicy.PROPOSED,
            answer_obligations=["continue_case_qualification", "ask_one_main_follow_up"],
            case_relevance=CaseRelevance.ACTIVE_CASE_CONTEXT if payload.active_case_exists else CaseRelevance.NEW_CASE_CANDIDATE,
            resume_strategy=ResumeStrategy.REEVALUATE_AFTER_ANSWER,
            task_stack=self._task_stack(payload),
            confidence=payload.pre_gate_confidence,
        )
