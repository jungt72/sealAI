from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Literal

from app.agent.communication.conversation_controller_v7 import (
    ConversationControllerInput,
    ConversationControllerV7,
)
from app.agent.communication.side_question_detection import (
    classify_message_as_knowledge_side_question,
    contains_concrete_case_marker,
)
from app.agent.communication.templates import render_communication_template
from app.agent.communication.v7_contracts import AnswerMode, TurnDecision
from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge_intent import has_technical_knowledge_subject

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CommunicationRuntimeV8DecisionProposal:
    intent: Literal[
        "smalltalk",
        "meta",
        "knowledge",
        "active_case_side_question",
        "governed_intake",
        "blocked",
        "unclear",
    ]
    confidence: float = 0.0
    reason: str = ""


def _communication_runtime_llm_enabled() -> bool:
    return os.environ.get("SEALAI_ENABLE_COMMUNICATION_RUNTIME_LLM", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class CommunicationRuntimeV8(ConversationControllerV7):
    """V8 single frontdoor turn decision before governed graph entry.

    The runtime decides the user's intent and allowed backend action once, before
    LangGraph. LangGraph remains the technical engine; it is entered only when
    the resulting RuntimeAction permits it.
    """

    async def decide(self, payload: ConversationControllerInput) -> TurnDecision:
        deterministic = self.decide_deterministic(payload)
        proposal = await self._llm_decision_proposal(payload, deterministic)
        if proposal is None:
            return deterministic
        return self._apply_safe_llm_proposal(payload, deterministic, proposal)

    def decide_deterministic(self, payload: ConversationControllerInput) -> TurnDecision:
        # V8 priority: safety, pending slot, process/meta, side questions,
        # knowledge, smalltalk, then governed intake.
        if payload.pre_gate_classification is PreGateClassification.BLOCKED:
            return self._blocked(payload)

        if payload.slot_answer_binding is not None:
            return self._pending_slot_answer(payload)

        if self._looks_like_process_question(payload.user_message):
            if payload.active_case_exists:
                return self._active_case_process_question(payload)
            return self._meta(payload)

        if payload.active_case_exists and self._looks_like_side_question(payload.user_message):
            return self._knowledge_or_side_question(payload)

        if payload.pre_gate_classification in {
            PreGateClassification.KNOWLEDGE_QUERY,
            PreGateClassification.DEEP_DIVE,
        }:
            return self._knowledge_or_side_question(payload)

        if payload.pre_gate_classification is PreGateClassification.GREETING:
            return self._smalltalk(payload)

        if payload.pre_gate_classification is PreGateClassification.META_QUESTION:
            return self._active_case_process_question(payload) if payload.active_case_exists else self._meta(payload)

        return self._governed_intake(payload)

    def _looks_like_side_question(self, message: str) -> bool:
        if classify_message_as_knowledge_side_question(message) is not None:
            return True
        return super()._looks_like_side_question(message)

    async def _llm_decision_proposal(
        self,
        payload: ConversationControllerInput,
        deterministic: TurnDecision,
    ) -> CommunicationRuntimeV8DecisionProposal | None:
        if not _communication_runtime_llm_enabled():
            return None
        # Safety and pending slot binding are deterministic authority.
        if payload.pre_gate_classification is PreGateClassification.BLOCKED:
            return None
        if payload.slot_answer_binding is not None:
            return None

        try:
            from app.llm.factory import get_async_llm  # noqa: PLC0415

            client, model = get_async_llm("communication_runtime")
            response = await client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=180,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": render_communication_template(
                            "communication_runtime_v8_system",
                            fallback=(
                                "You are SeaLAI Communication Runtime V8. Classify the "
                                "latest user turn only. Return JSON with keys intent, "
                                "confidence, reason. Do not answer the user. Do not set "
                                "engineering truth. Valid intents: smalltalk, meta, "
                                "knowledge, active_case_side_question, governed_intake, "
                                "blocked, unclear."
                            ),
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "message": payload.user_message,
                                "pre_gate": payload.pre_gate_classification.value,
                                "active_case_exists": payload.active_case_exists,
                                "pending_question_target": (
                                    payload.pending_question.target_field
                                    if payload.pending_question is not None
                                    else None
                                ),
                                "deterministic_answer_mode": deterministic.answer_mode.value,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            )
            raw = response.choices[0].message.content if response.choices else ""
            data = json.loads(str(raw or "{}"))
            intent = str(data.get("intent") or "unclear").strip()
            if intent not in {
                "smalltalk",
                "meta",
                "knowledge",
                "active_case_side_question",
                "governed_intake",
                "blocked",
                "unclear",
            }:
                return None
            return CommunicationRuntimeV8DecisionProposal(
                intent=intent,  # type: ignore[arg-type]
                confidence=float(data.get("confidence") or 0.0),
                reason=str(data.get("reason") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            log.info(
                "[communication_runtime_v8] LLM proposal unavailable (%s)",
                type(exc).__name__,
            )
            return None

    def _apply_safe_llm_proposal(
        self,
        payload: ConversationControllerInput,
        deterministic: TurnDecision,
        proposal: CommunicationRuntimeV8DecisionProposal,
    ) -> TurnDecision:
        if proposal.confidence < 0.72:
            return deterministic

        current_mode = deterministic.answer_mode
        if current_mode in {
            AnswerMode.SAFETY_BLOCKED,
            AnswerMode.PENDING_SLOT_ANSWER,
            AnswerMode.GOVERNED_INTAKE,
        } and proposal.intent not in {"knowledge", "active_case_side_question", "smalltalk", "meta"}:
            return deterministic

        if proposal.intent == "smalltalk" and not contains_concrete_case_marker(payload.user_message):
            return self._smalltalk(payload)

        if proposal.intent == "meta":
            return self._active_case_process_question(payload) if payload.active_case_exists else self._meta(payload)

        if proposal.intent in {"knowledge", "active_case_side_question"}:
            # Concrete operating data still belongs to governed intake.
            if contains_concrete_case_marker(payload.user_message):
                return deterministic
            if classify_message_as_knowledge_side_question(payload.user_message) is None:
                if proposal.intent != "knowledge" or not has_technical_knowledge_subject(payload.user_message):
                    return deterministic
            return self._knowledge_or_side_question(payload)

        return deterministic
