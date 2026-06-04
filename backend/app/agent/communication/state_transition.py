from __future__ import annotations

from app.agent.communication.models import (
    CaseConversationState,
    ConversationCommand,
    ConversationMode,
    ProposedFieldUpdate,
    SpeechAct,
    StateTransitionDecision,
)
from app.agent.communication.speech_act import has_act


class StateTransitionGuard:
    """Decides whether a turn is allowed to advance governed case state.

    This is intentionally deterministic. The LLM may make conversation pleasant,
    but it must not turn thanks, isolated yes/no answers, or "I don't know" into
    technical progress.
    """

    _NO_PROGRESS_ACTS = {
        "social.greeting",
        "social.thanks",
        "task.free_text",
        "task.empty",
        "meta.ask_explain",
    }

    def evaluate(
        self,
        *,
        state: CaseConversationState,
        mode: ConversationMode,
        speech_acts: list[SpeechAct],
        proposed_updates: list[ProposedFieldUpdate],
        language: str = "de",
    ) -> StateTransitionDecision:
        acts = {act.label for act in speech_acts}
        allowed_updates = [] if mode is ConversationMode.GENERAL_KNOWLEDGE else list(proposed_updates)
        answers_active_question = self._answers_active_question(
            state=state,
            updates=allowed_updates,
        )

        if mode is ConversationMode.OUT_OF_SCOPE_OR_UNSAFE:
            return self._block(
                reasons=["unsafe_or_out_of_scope"],
                commands=[self._command("RefuseUnsafeInstruction", "Unsafe instruction cannot advance state.")],
                speech_acts=speech_acts,
                language=language,
                answers_active_question=False,
                fallback_level=1,
                human_handoff=False,
            )

        if "meta.cancel" in acts:
            return self._block(
                reasons=["cancel_requested"],
                commands=[self._command("StopCurrentStep", "User asked to stop or postpone the current step.")],
                speech_acts=speech_acts,
                language=language,
                answers_active_question=False,
                fallback_level=1,
            )

        if "task.unknown" in acts:
            return self._block(
                reasons=["unknown_is_not_progress"],
                commands=[self._command("MarkUnknown", "Unknown answer must not be treated as resolved.")],
                speech_acts=speech_acts,
                language=language,
                answers_active_question=False,
                fallback_level=1,
            )

        if (has_act(speech_acts, "confirm.yes") or has_act(speech_acts, "confirm.no")) and not state.pending_confirmation:
            if not allowed_updates:
                return self._block(
                    reasons=["confirmation_without_pending_action"],
                    commands=[self._command("AskClarification", "No pending confirmation exists for this yes/no answer.")],
                    speech_acts=speech_acts,
                    language=language,
                    answers_active_question=False,
                    fallback_level=1,
                )

        if mode is ConversationMode.GENERAL_KNOWLEDGE:
            return StateTransitionDecision(
                decision="block_progress",
                reasons=["general_knowledge_no_state_patch"],
                commands=[self._command("AnswerKnowledgeQuestion", "Knowledge answer must not change case state.")],
                state_patch_size=0,
                allowed_proposed_updates=[],
                speech_acts=speech_acts,
                language=language,
                answers_active_question=False,
                fallback_level=0,
                human_handoff=False,
            )

        if not allowed_updates:
            reasons = ["no_slot_evidence"]
            commands: list[ConversationCommand] = []
            if "task.intent_to_start" in acts:
                reasons.insert(0, "intent_to_start_case")
                commands.append(
                    self._command(
                        "AcknowledgeIntentAndAskNextQuestion",
                        "User wants to start or continue case clarification.",
                    )
                )
            if acts and any(label.startswith("social.") for label in acts) and acts.issubset(self._NO_PROGRESS_ACTS):
                reasons.insert(0, "social_only_utterance")
                commands.append(self._command("AcknowledgeWithoutProgress", "Turn contains no technical slot evidence."))
            if state.active_question or state.allowed_next_actions:
                commands.append(self._command("RepeatOrReframeQuestion", "Continue with the current best next question."))
            return self._block(
                reasons=reasons,
                commands=commands or [self._command("AskNextQuestion", "No governed state patch is available.")],
                speech_acts=speech_acts,
                language=language,
                answers_active_question=False,
                fallback_level=0,
            )

        return StateTransitionDecision(
            decision="allow_transition",
            reasons=["slot_evidence_present"],
            commands=[
                self._command(
                    "SetSlotCandidate",
                    "User text contains a candidate value; governor must validate it.",
                    field_key=item.key,
                )
                for item in allowed_updates
            ],
            state_patch_size=len(allowed_updates),
            allowed_proposed_updates=allowed_updates,
            speech_acts=speech_acts,
            language=language,
            answers_active_question=answers_active_question,
            fallback_level=0,
            human_handoff=False,
        )

    @staticmethod
    def _command(name: str, reason: str, field_key: str | None = None) -> ConversationCommand:
        return ConversationCommand(type="conversation_command", name=name, field_key=field_key, reason=reason)

    @staticmethod
    def _block(
        *,
        reasons: list[str],
        commands: list[ConversationCommand],
        speech_acts: list[SpeechAct],
        language: str,
        answers_active_question: bool | None,
        fallback_level: int,
        human_handoff: bool = False,
    ) -> StateTransitionDecision:
        return StateTransitionDecision(
            decision="block_progress",
            reasons=reasons,
            commands=commands,
            state_patch_size=0,
            allowed_proposed_updates=[],
            speech_acts=speech_acts,
            language=language,
            answers_active_question=answers_active_question,
            fallback_level=fallback_level,
            human_handoff=human_handoff,
        )

    @staticmethod
    def _answers_active_question(
        *,
        state: CaseConversationState,
        updates: list[ProposedFieldUpdate],
    ) -> bool | None:
        if not state.active_question and not state.active_question_field_keys:
            return None
        update_keys = {item.key for item in updates}
        active_keys = {str(key).strip() for key in state.active_question_field_keys if str(key).strip()}
        if active_keys and update_keys:
            return bool(update_keys.intersection(active_keys))
        if not updates:
            return False
        question = str(state.active_question or "").casefold()
        return any(str(item.key).replace("_", " ").casefold() in question for item in updates)
