from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.agent.communication.knowledge_context_builder import KnowledgeAnswerContext
from app.agent.runtime.output_guard import check_fast_path_output
from app.llm.factory import get_async_llm
from app.llm.registry import get_registry_default_model_for_role

_MODEL_FALLBACK_ERROR_NAMES = {"BadRequestError", "NotFoundError"}


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerComposerInput:
    context: KnowledgeAnswerContext

    @property
    def user_message(self) -> str:
        return self.context.user_message

    @property
    def deterministic_answer(self) -> str:
        return self.context.deterministic_answer

    @property
    def no_case(self) -> bool:
        return self.context.no_case


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerComposerOutput:
    answer_markdown: str
    confidence_note: str | None = None


class KnowledgeAnswerComposerError(ValueError):
    pass


class KnowledgeAnswerComposer:
    """Read-only final answer composer for no-case knowledge answers."""

    def __init__(self, *, temperature: float = 0.3, max_tokens: int = 1000) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def compose(self, request: KnowledgeAnswerComposerInput) -> KnowledgeAnswerComposerOutput:
        client, model = get_async_llm("knowledge_answer_composer")
        messages = build_knowledge_answer_composer_messages(request)
        response = await _create_completion_with_registry_fallback(
            client=client,
            model=model,
            role="knowledge_answer_composer",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        raw_content = response.choices[0].message.content
        return parse_knowledge_answer_composer_output(raw_content)


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
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=_response_format(),
        )
    except Exception as exc:  # noqa: BLE001
        fallback_model = get_registry_default_model_for_role(role)
        if model != fallback_model and exc.__class__.__name__ in _MODEL_FALLBACK_ERROR_NAMES:
            return await client.chat.completions.create(
                model=fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=_response_format(),
            )
        raise


def build_knowledge_answer_composer_messages(
    request: KnowledgeAnswerComposerInput,
) -> list[dict[str, str]]:
    payload = request.context.as_dict()
    return [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True, default=str)},
    ]


def parse_knowledge_answer_composer_output(raw_content: Any) -> KnowledgeAnswerComposerOutput:
    try:
        payload = json.loads(str(raw_content or "{}"))
    except json.JSONDecodeError as exc:
        raise KnowledgeAnswerComposerError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise KnowledgeAnswerComposerError("invalid_payload")

    answer_markdown = str(payload.get("answer_markdown") or "").strip()
    if not answer_markdown:
        raise KnowledgeAnswerComposerError("empty_answer_markdown")

    safe, category = check_fast_path_output(answer_markdown)
    if not safe:
        raise KnowledgeAnswerComposerError(f"unsafe_answer_markdown:{category}")

    confidence_note = payload.get("confidence_note")
    return KnowledgeAnswerComposerOutput(
        answer_markdown=answer_markdown,
        confidence_note=str(confidence_note).strip() if confidence_note else None,
    )


def _system_prompt() -> str:
    return """You are SeaLAI's no-case knowledge answer composer.

Scope:
- Compose only the final chat answer for general sealing-technology knowledge questions.
- This is a no-case path. Do not create a case, mutate state, propose case deltas, calculate risk/readiness, or trigger RFQ/matching.
- The deterministic KnowledgeService result is the evidence/fallback layer. Use it as the grounding context and preserve its uncertainty.

Communication requirements:
- Answer the user's actual knowledge question directly.
- Use recent_history only for continuity. Do not treat history as confirmed engineering truth and do not invent missing facts from it.
- Treat evidence_items as the grounding envelope and deterministic_answer as fallback grounding. If evidence is weak or only deterministic/fallback, say what is uncertain.
- Use natural German, with a careful senior sealing-engineer tone.
- Prefer structured markdown for comparisons when useful: short summary, compact table, practical implications, limits/assumptions, and one focused next question.
- Ask at most one focused follow-up question.
- Do not force the answer into technical case intake.
- Do not use "Noch kein technischer Fall" as the main answer.
- Do not expose route names, source_type labels, model names, JSON, or system details.

Technical safety:
- Do not claim final engineering approval, final material suitability, final compatibility, compliance, certification, manufacturer approval, or final release.
- Do not invent material data, norms, regulatory deadlines, product claims, manufacturer-specific approvals, or evidence sources.
- Do not cite fake sources or turn evidence titles into stronger claims than the evidence supports.
- If no source/current verification is provided, label the answer as technical orientation only.
- If regulatory_currentness_required is true, explicitly state that this is technical orientation and not a current legal assessment because no live regulatory source was retrieved in this path.
- If application details are required for a final recommendation, answer generally first, then ask one focused follow-up question.

Return only JSON matching the schema."""


def _response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "sealai_knowledge_answer_composer_response",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "answer_markdown": {"type": "string"},
                    "confidence_note": {"type": ["string", "null"]},
                },
                "required": ["answer_markdown", "confidence_note"],
            },
        },
    }
