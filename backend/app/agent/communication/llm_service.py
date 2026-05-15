from __future__ import annotations

import json
import os
from typing import Any, Callable, Protocol

import openai

from app.agent.communication.models import (
    AllowedClaim,
    CaseConversationState,
    ConversationMode,
    LLMResponseContract,
)
from app.observability.langsmith import traceable, wrap_openai_client


HUMAN_COMMUNICATION_PROMPT_VERSION = "sealai_human_communication_v2"


class HumanCommunicationLLM(Protocol):
    model_name: str
    provider_name: str

    @traceable(name="sealai.human_communication_response", run_type="llm")
    async def create_response(
        self,
        *,
        mode: ConversationMode,
        state: CaseConversationState,
        allowed_claims: list[AllowedClaim],
        proposed_field_updates: list[dict[str, Any]],
    ) -> LLMResponseContract: ...


class OpenAIHumanCommunicationLLMService:
    """Structured LLM adapter for the human communication layer."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("SEALAI_CONVERSATION_MODEL", "gpt-4o-mini")
        self._client_factory = client_factory or openai.AsyncOpenAI

    async def create_response(
        self,
        *,
        mode: ConversationMode,
        state: CaseConversationState,
        allowed_claims: list[AllowedClaim],
        proposed_field_updates: list[dict[str, Any]],
    ) -> LLMResponseContract:
        client = wrap_openai_client(self._client_factory())
        response = await client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": build_human_communication_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "mode": mode.value,
                            "case_state": state.model_dump(mode="json", exclude={"user_id", "tenant_id"}),
                            "allowed_claims": [claim.model_dump(mode="json") for claim in allowed_claims],
                            "proposed_field_updates": proposed_field_updates,
                        },
                        ensure_ascii=True,
                        default=str,
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=700,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "sealai_human_communication_response",
                    "strict": True,
                    "schema": _response_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        return LLMResponseContract.model_validate_json(str(content or "{}"))


def build_human_communication_system_prompt() -> str:
    return """You are SealAI's Human Communication Layer.

You communicate like a careful, helpful senior sealing-technology engineer. Your job is to make the backend's technical state understandable to the user.

You may explain, summarize, ask clarifying questions, and guide the user.

You must not create engineering truth.

The backend state, deterministic calculations, rules, risks, readiness status, evidence references, and allowed_claims are the only source for concrete case-bound statements.

For general sealing knowledge, explain broadly and use uncertainty language. Do not turn general knowledge into a concrete recommendation.

For a concrete sealing case, only state what is grounded in allowed_claims. Clearly distinguish confirmed data, missing data, proposed data, stale data, calculated values, and backend-identified risks.
If you cite evidence, include the exact evidence_ref_id in cited_evidence_ref_ids. Do not cite evidence that is not provided.
Do not introduce new proposed field updates. You may only echo proposed_field_updates that were provided in the input, and they must keep requires_user_confirmation=true.

Communication style:
- Do not repeat the full current case state in every answer. The cockpit already shows the working state.
- Mention concrete values only when they are newly recognized, corrected, conflicting, stale, directly asked for, or needed to answer a final summary/RFQ-preview request.
- For normal case qualification, sound like a human engineer: short acknowledgement, one useful explanation, then the next precise question.
- Avoid internal labels such as "Arbeitsstand", "aktuell verstanden", "Dichtungstyp-Richtung", "Next Best Question", "Readiness" unless the user explicitly asks for status details.
- Summarize all known facts only near the end of a case, for RFQ preview, or when the user asks for a summary.

Never silently assume missing values.
Never fabricate evidence.
Never fabricate standards.
Never fabricate manufacturer statements.
Never approve a final sealing solution.
Never say a material, design, supplier, or sealing solution is finally approved unless the backend explicitly provides such an approval claim.
Never override deterministic services.

If critical data is missing, ask for the most important missing fields.
If the user asks for a final decision and the backend does not provide one, explain what is still needed and state that final approval must come from the responsible manufacturer, engineering authority, or qualified expert.

Return only valid JSON matching the required response contract."""


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "mode": {
                "type": "string",
                "enum": [mode.value for mode in ConversationMode],
            },
            "assistant_message": {"type": "string"},
            "used_claim_ids": {"type": "array", "items": {"type": "string"}},
            "cited_evidence_ref_ids": {"type": "array", "items": {"type": "string"}},
            "asks_for_fields": {"type": "array", "items": {"type": "string"}},
            "proposed_field_updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "key": {"type": "string"},
                        "value": {},
                        "unit": {"type": ["string", "null"]},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "requires_user_confirmation": {"type": "boolean"},
                    },
                    "required": ["key", "value", "unit", "confidence", "requires_user_confirmation"],
                },
            },
            "recommendation_level": {
                "type": "string",
                "enum": ["none", "directional", "requires_review"],
            },
            "contains_solution_recommendation": {"type": "boolean"},
            "contains_final_approval": {"type": "boolean"},
            "requires_human_review": {"type": "boolean"},
            "safety_flags": {"type": "array", "items": {"type": "string"}},
            "next_action": {"type": ["string", "null"]},
        },
        "required": [
            "mode",
            "assistant_message",
            "used_claim_ids",
            "cited_evidence_ref_ids",
            "asks_for_fields",
            "proposed_field_updates",
            "recommendation_level",
            "contains_solution_recommendation",
            "contains_final_approval",
            "requires_human_review",
            "safety_flags",
            "next_action",
        ],
    }
