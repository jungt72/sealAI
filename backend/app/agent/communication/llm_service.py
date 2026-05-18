from __future__ import annotations

import json
import os
from typing import Any, Callable, Protocol

import openai

from app.agent.prompts import prompts
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
    return prompts.render(
        "communication/human_layer.j2",
        {"prompt_version": HUMAN_COMMUNICATION_PROMPT_VERSION},
    )


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
