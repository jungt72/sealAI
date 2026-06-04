from __future__ import annotations

import inspect
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

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
from app.llm.registry import get_registry_default_model_for_role
from app.services.openai_payload import use_responses_api
from app.services.knowledge_intent import has_technical_knowledge_subject

log = logging.getLogger(__name__)

_MODEL_FALLBACK_ERROR_NAMES = {"BadRequestError", "NotFoundError"}

_ENGINEERING_ASSESSMENT_MARKERS = (
    "bewerte",
    "beurteile",
    "einschaetzung",
    "einschätzung",
    "screening",
    "empfehl",
    "geeignet",
    "eignung",
    "kann ich",
    "soll ich",
    "nehmen",
    "verwenden",
)
_CASE_ENGINEERING_SUBJECT_MARKERS = (
    "ptfe",
    "fkm",
    "ffkm",
    "epdm",
    "nbr",
    "hnbr",
    "rwdr",
    "radialwellendichtring",
    "gleitringdichtung",
    "o-ring",
    "oring",
    "werkstoff",
    "material",
    "dichtung",
)


@dataclass(frozen=True, slots=True)
class CommunicationRuntimeV8DecisionProposal:
    intent: Literal[
        "smalltalk",
        "meta",
        "knowledge",
        "active_case_side_question",
        "pending_slot_answer",
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

        if self._is_technical_case_challenge(payload):
            return self._technical_case_challenge(payload)

        if self._looks_like_process_question(payload.user_message):
            if payload.active_case_exists:
                return self._active_case_process_question(payload)
            return self._meta(payload)

        if payload.active_case_exists and self._looks_like_case_specific_engineering_request(
            payload.user_message
        ):
            return self._governed_intake(payload)

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

    def _looks_like_case_specific_engineering_request(self, message: str) -> bool:
        normalized = " ".join((message or "").casefold().split())
        if not normalized:
            return False
        if not contains_concrete_case_marker(normalized):
            return False
        has_assessment_intent = any(
            marker in normalized for marker in _ENGINEERING_ASSESSMENT_MARKERS
        )
        has_engineering_subject = any(
            marker in normalized for marker in _CASE_ENGINEERING_SUBJECT_MARKERS
        )
        return has_assessment_intent and has_engineering_subject

    async def _llm_decision_proposal(
        self,
        payload: ConversationControllerInput,
        deterministic: TurnDecision,
    ) -> CommunicationRuntimeV8DecisionProposal | None:
        if not _communication_runtime_llm_enabled():
            return None
        # Safety remains deterministic authority. Pending slot bindings are only
        # candidates here; the semantic runtime may veto them before mutation.
        if payload.pre_gate_classification is PreGateClassification.BLOCKED:
            return None

        try:
            from app.llm.factory import get_async_llm  # noqa: PLC0415

            client, model = get_async_llm("communication_runtime")
            messages = [
                {
                    "role": "system",
                    "content": render_communication_template(
                        "communication_runtime_v8_system",
                        fallback=(
                            "You are SeaLAI Communication Runtime V8. Classify the "
                            "latest user turn by semantic intent, not by keywords. "
                            "Return JSON with keys intent, confidence, reason. Do not "
                            "answer the user. Valid intents: smalltalk, meta, "
                            "knowledge, active_case_side_question, pending_slot_answer, "
                            "governed_intake, blocked, unclear."
                        ),
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        _semantic_runtime_payload(
                            payload=payload,
                            deterministic=deterministic,
                        ),
                        ensure_ascii=False,
                    ),
                },
            ]
            response = await _create_completion_with_registry_fallback(
                client=client,
                model=model,
                role="communication_runtime",
                messages=messages,
                temperature=0.1,
                max_tokens=220,
            )
            raw = response.choices[0].message.content if response.choices else ""
            data = json.loads(str(raw or "{}"))
            intent = str(data.get("intent") or "unclear").strip()
            if intent not in {
                "smalltalk",
                "meta",
                "knowledge",
                "active_case_side_question",
                "pending_slot_answer",
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

        if proposal.intent == "blocked":
            return self._blocked(payload)

        if proposal.intent == "pending_slot_answer":
            if payload.slot_answer_binding is not None:
                return self._pending_slot_answer(payload)
            return deterministic

        current_mode_value = _answer_mode_value(deterministic)
        if (
            payload.slot_answer_binding is not None
            and current_mode_value == AnswerMode.PENDING_SLOT_ANSWER.value
            and proposal.intent in {"knowledge", "active_case_side_question"}
            and classify_message_as_knowledge_side_question(payload.user_message) is None
        ):
            return deterministic
        if current_mode_value == AnswerMode.TECHNICAL_CASE_CHALLENGE.value:
            return deterministic
        if current_mode_value in {
            AnswerMode.SAFETY_BLOCKED.value,
            AnswerMode.PENDING_SLOT_ANSWER.value,
            AnswerMode.TECHNICAL_CASE_CHALLENGE.value,
            AnswerMode.GOVERNED_INTAKE.value,
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

        if (
            proposal.intent == "unclear"
            and payload.active_case_exists
            and payload.pending_question is not None
        ):
            return self._active_case_process_question(payload)

        return deterministic


async def _create_completion_with_registry_fallback(
    *,
    client: Any,
    model: str,
    role: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> Any:
    try:
        if use_responses_api(model):
            instructions, response_input = _responses_input_from_messages(messages)
            response_or_awaitable = client.responses.create(
                model=model,
                instructions=instructions or None,
                input=response_input,
                max_output_tokens=max_tokens,
            )
            response = (
                await response_or_awaitable
                if inspect.isawaitable(response_or_awaitable)
                else response_or_awaitable
            )
            return _completion_response_from_text(_extract_responses_text(response))
        return await client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except Exception as exc:  # noqa: BLE001
        fallback_model = get_registry_default_model_for_role(role)
        if model != fallback_model and exc.__class__.__name__ in _MODEL_FALLBACK_ERROR_NAMES:
            log.warning(
                "[communication_runtime_v8] configured model rejected; retrying registry default"
            )
            if use_responses_api(fallback_model):
                instructions, response_input = _responses_input_from_messages(messages)
                response_or_awaitable = client.responses.create(
                    model=fallback_model,
                    instructions=instructions or None,
                    input=response_input,
                    max_output_tokens=max_tokens,
                )
                response = (
                    await response_or_awaitable
                    if inspect.isawaitable(response_or_awaitable)
                    else response_or_awaitable
                )
                return _completion_response_from_text(_extract_responses_text(response))
            return await client.chat.completions.create(
                model=fallback_model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=messages,
            )
        raise


def _semantic_runtime_payload(
    *,
    payload: ConversationControllerInput,
    deterministic: TurnDecision,
) -> dict[str, Any]:
    pending_question = payload.pending_question
    slot_binding = payload.slot_answer_binding
    return {
        "message": payload.user_message,
        "pre_gate": payload.pre_gate_classification.value,
        "active_case_exists": payload.active_case_exists,
        "pending_question": (
            {
                "target_field": pending_question.target_field,
                "expected_answer_type": pending_question.expected_answer_type,
                "question_text": pending_question.question_text,
                "ambiguity_policy": pending_question.ambiguity_policy,
                "status": pending_question.status,
            }
            if pending_question is not None
            else None
        ),
        "deterministic_answer_mode": _answer_mode_value(deterministic),
        "deterministic_slot_binding": (
            {
                "target_field": slot_binding.target_field,
                "raw_value": slot_binding.raw_value,
                "normalized_value": slot_binding.normalized_value,
                "confidence": slot_binding.confidence,
                "ambiguity": slot_binding.ambiguity,
                "needs_clarification": slot_binding.needs_clarification,
            }
            if slot_binding is not None
            else None
        ),
        "decision_task": (
            "Decide whether the latest message actually answers the pending "
            "question, or whether it is social/acknowledgement, meta/process, "
            "knowledge, side-question, new governed case data, blocked, or unclear."
        ),
    }


def _answer_mode_value(decision: TurnDecision) -> str:
    mode = getattr(decision, "answer_mode", "")
    return str(getattr(mode, "value", mode) or "")


def _responses_input_from_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    instructions: list[str] = []
    response_input: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user").strip()
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            instructions.append(content)
            continue
        is_assistant = role == "assistant"
        # OpenAI Responses API content typing is role-specific: assistant turns
        # must use "output_text", user turns "input_text". Sending "input_text"
        # for an assistant history message raises a 400 (invalid_value) on every
        # follow-up turn — only the first turn (no assistant history) survived.
        response_input.append(
            {
                "role": "assistant" if is_assistant else "user",
                "content": [
                    {
                        "type": "output_text" if is_assistant else "input_text",
                        "text": content,
                    }
                ],
            }
        )
    return "\n\n".join(instructions), response_input


def _extract_responses_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    output = getattr(response, "output", None)
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for part in content:
                text = getattr(part, "text", None)
                if text:
                    parts.append(str(text))
        if parts:
            return "".join(parts)
    if isinstance(response, dict):
        output_text = response.get("output_text")
        if output_text:
            return str(output_text)
        parts = []
        for item in response.get("output", []) or []:
            for part in item.get("content", []) or []:
                text = part.get("text")
                if text:
                    parts.append(str(text))
        if parts:
            return "".join(parts)
    return ""


def _completion_response_from_text(text: str) -> Any:
    class Message:
        pass

    class Choice:
        pass

    class Response:
        pass

    message = Message()
    message.content = text
    choice = Choice()
    choice.message = message
    response = Response()
    response.choices = [choice]
    return response
