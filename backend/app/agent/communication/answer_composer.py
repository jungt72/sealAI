from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.agent.communication.knowledge_context_builder import KnowledgeAnswerContext
from app.agent.communication.templates import render_communication_template
from app.agent.runtime.output_guard import check_fast_path_output
from app.llm.factory import get_async_llm
from app.llm.registry import get_registry_default_model_for_role
from app.services.knowledge.material_comparison import extract_material_ids, supported_material_ids

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
        output = parse_knowledge_answer_composer_output(raw_content)
        output = enforce_requested_subject_fidelity(request, output)
        output = compact_simple_definition_answer(request, output)
        return enforce_requested_subject_fidelity(request, output)


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


_SIMPLE_DEFINITION_PATTERNS = (
    r"\bwas\s+ist\b",
    r"\bwas\s+bedeutet\b",
    r"\bwas\s+kannst\s+du\s+mir\s+zu\b",
    r"\berkl[aä]r(?:e|en)?\b",
)
_COMPARISON_MARKERS = (
    "vergleich",
    "unterschied",
    " vs ",
    " versus ",
    " gegenüber ",
    " gegen ",
)


def compact_simple_definition_answer(
    request: KnowledgeAnswerComposerInput,
    output: KnowledgeAnswerComposerOutput,
) -> KnowledgeAnswerComposerOutput:
    """Keep simple material-definition answers direct and product-like."""

    if not _is_simple_material_definition_question(request.user_message):
        return output

    requested = _single_requested_material(request)
    if requested and requested not in extract_material_ids(request.deterministic_answer):
        return output

    compact = _compact_from_deterministic_answer(request.deterministic_answer)
    if not compact:
        return output
    return KnowledgeAnswerComposerOutput(
        answer_markdown=compact,
        confidence_note=output.confidence_note,
    )


def _is_simple_material_definition_question(user_message: str) -> bool:
    text = str(user_message or "").strip()
    if not text:
        return False
    lowered = f" {text.casefold()} "
    if any(marker in lowered for marker in _COMPARISON_MARKERS):
        return False
    if not any(re.search(pattern, lowered) for pattern in _SIMPLE_DEFINITION_PATTERNS):
        return False
    materials = set(extract_material_ids(text))
    return len(materials) == 1


def enforce_requested_subject_fidelity(
    request: KnowledgeAnswerComposerInput,
    output: KnowledgeAnswerComposerOutput,
) -> KnowledgeAnswerComposerOutput:
    """Reject visible answers that drift away from the latest requested material."""

    requested = _single_requested_material(request)
    if not requested:
        return output

    answer = str(output.answer_markdown or "")
    answer_materials = extract_material_ids(answer)
    if requested not in answer_materials and requested.casefold() not in answer.casefold():
        raise KnowledgeAnswerComposerError("requested_subject_missing")

    first_materials = extract_material_ids(answer[:500])
    if first_materials and first_materials[0] != requested:
        raise KnowledgeAnswerComposerError("requested_subject_drift")

    _reject_unscoped_material_suitability_claim(answer)

    return output


def _single_requested_material(request: KnowledgeAnswerComposerInput) -> str | None:
    requested = tuple(getattr(request.context, "requested_subjects", ()) or ())
    if len(requested) == 1:
        return requested[0]
    fallback = extract_material_ids(request.user_message)
    if len(fallback) == 1:
        return fallback[0]
    return None


_MATERIAL_CLAIM_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(material_id) for material_id in supported_material_ids())
    + r")\b[^.\n]{0,180}\b(?:ist\s+(?:gut\s+)?geeignet|geeignet\s+ist)\b",
    re.IGNORECASE | re.UNICODE,
)


def _reject_unscoped_material_suitability_claim(answer_markdown: str) -> None:
    for match in _MATERIAL_CLAIM_RE.finditer(str(answer_markdown or "")):
        window = str(answer_markdown or "")[max(0, match.start() - 60) : match.end()].casefold()
        if "nicht geeignet" in window or "nicht automatisch geeignet" in window:
            continue
        raise KnowledgeAnswerComposerError("unsafe_material_suitability_claim")


def _compact_from_deterministic_answer(deterministic_answer: str) -> str:
    text = str(deterministic_answer or "").strip()
    if not text:
        return ""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    lead_source = re.split(r"\bTypische Orientierung:\s*", text, maxsplit=1)[0]
    lead = _single_line(lead_source or (paragraphs[0] if paragraphs else ""))
    bullets = _extract_orientation_bullets(text)
    selected_bullets = [bullet for bullet in bullets if bullet][:2]
    closing = (
        "Für eine konkrete Eignung brauche ich Medium, Temperatur und "
        "Betriebsart; Herstellerprüfung bleibt erforderlich. Das ist "
        "technische Orientierung, keine technische Freigabe."
    )
    parts = [lead]
    if selected_bullets:
        parts.append("Kurz eingeordnet:")
        parts.extend(f"- {bullet}" for bullet in selected_bullets)
    parts.append(closing)
    return "\n".join(part for part in parts if part).strip()


def _extract_orientation_bullets(text: str) -> list[str]:
    match = re.search(r"\bTypische Orientierung:\s*(?P<section>.*)", text, flags=re.DOTALL)
    if not match:
        return [
            _single_line(line.lstrip("- ").strip())
            for line in text.splitlines()
            if line.strip().startswith("- ")
        ]
    section = re.split(
        r"\b(?:Für eine konkrete|Bis dahin|Wenn das Ihr konkreter)\b",
        match.group("section"),
        maxsplit=1,
    )[0]
    chunks = re.split(r"(?:^|\s)-\s+", section)
    return [_single_line(chunk) for chunk in chunks if _single_line(chunk)]


def _single_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _system_prompt() -> str:
    fallback = """You are SeaLAI's no-case knowledge answer composer.

Scope:
- Compose only the final chat answer for general sealing-technology knowledge questions.
- This is a no-case path. Do not create a case, mutate state, propose case deltas, calculate risk/readiness, or trigger RFQ/matching.
- The deterministic KnowledgeService result is the evidence/fallback layer. Use it as the grounding context and preserve its uncertainty.

Communication requirements:
- Answer the user's actual knowledge question directly.
- If requested_subjects contains exactly one material, the latest user message is authoritative: start with that material and do not switch to a different material from recent_history or evidence_items.
- Use recent_history only for continuity. Do not treat history as confirmed engineering truth and do not invent missing facts from it.
- Treat evidence_items as the grounding envelope and deterministic_answer as fallback grounding. If evidence is weak or only deterministic/fallback, say what is uncertain.
- Use natural German, with a careful senior sealing-engineer tone.
- Prefer structured markdown for comparisons when useful: short summary, compact table, practical implications, limits/assumptions, and one focused next question.
- For simple definition questions about one material such as "Was ist NBR?", answer compactly: direct definition, 1-3 practical orientation points, and only one short caveat. Avoid generic section boilerplate such as "Limitierungen/Annahmen" unless the user asks for a deeper assessment.
- Prefer wording such as "wird geprüft", "wird betrachtet", "ist naheliegend zu prüfen" or "kann ein Kandidat sein". Do not write that a material "ist geeignet" or "für ... geeignet ist" in this knowledge path.
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
    return render_communication_template("knowledge_answer_composer_system", fallback=fallback)


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
