from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.agent.communication.knowledge_context_builder import KnowledgeAnswerContext
from app.agent.prompts import prompts
from app.agent.runtime.output_guard import check_fast_path_output
from app.llm.factory import get_async_llm
from app.llm.registry import get_registry_default_model_for_role
from app.services.knowledge.material_comparison import (
    extract_material_ids,
    supported_material_ids,
)

_MODEL_FALLBACK_ERROR_NAMES = {"BadRequestError", "NotFoundError"}
KNOWLEDGE_ANSWER_COMPOSER_PROMPT_VERSION = "sealai_knowledge_answer_composer_v2"


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

    def __init__(self, *, temperature: float = 0.35, max_tokens: int = 1800) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def compose(
        self, request: KnowledgeAnswerComposerInput
    ) -> KnowledgeAnswerComposerOutput:
        client, model = get_async_llm("knowledge_answer_composer")
        messages = build_knowledge_answer_composer_messages(request)
        try:
            return await self._compose_with_messages(
                request=request,
                client=client,
                model=model,
                messages=messages,
            )
        except KnowledgeAnswerComposerError as exc:
            if not _should_retry_visible_answer(exc):
                raise
            repair_messages = build_knowledge_answer_repair_messages(
                request,
                rejected_reason=str(exc),
            )
            return await self._compose_with_messages(
                request=request,
                client=client,
                model=model,
                messages=repair_messages,
            )

    async def _compose_with_messages(
        self,
        *,
        request: KnowledgeAnswerComposerInput,
        client: Any,
        model: str,
        messages: list[dict[str, str]],
    ) -> KnowledgeAnswerComposerOutput:
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
        output = enforce_material_comparison_depth(request, output)
        output = enforce_material_overview_depth(request, output)
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
        if (
            model != fallback_model
            and exc.__class__.__name__ in _MODEL_FALLBACK_ERROR_NAMES
        ):
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
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=True, default=str),
        },
    ]


def build_knowledge_answer_repair_messages(
    request: KnowledgeAnswerComposerInput,
    *,
    rejected_reason: str,
) -> list[dict[str, str]]:
    messages = build_knowledge_answer_composer_messages(request)
    repair_payload = {
        "repair_instruction": (
            "Rewrite the visible answer using the same payload. Return only the "
            "required JSON schema. Keep the latest user material subject "
            "authoritative. Avoid final suitability wording, especially 'ist "
            "geeignet', 'geeignet ist', 'gut geeignet', 'eignet sich fuer', "
            "'geeignet macht' and 'gute Eignung fuer'. "
            "Never state or imply that one material is better, more suitable, "
            "preferable or superior to another for an application; compare "
            "strictly symmetrically and name the missing decision parameters "
            "instead of ranking. "
            "Use cautious wording such as 'wird geprueft', 'wird betrachtet', "
            "'naheliegend zu pruefen' or 'kann ein Kandidat sein'. If the "
            "rejected reason is material_overview_too_shallow, expand the answer "
            "with practical sealing-engineering depth instead of returning a "
            "glossary card. If the rejected reason is "
            "material_comparison_too_shallow, provide a real engineering "
            "comparison with hard orientation values, limits and decision "
            "criteria for exactly the requested materials. If the rejected "
            "reason is material_comparison_too_broad, keep the same comparison "
            "axes but remove encyclopedia-style background and repetition."
        ),
        "rejected_reason": rejected_reason,
    }
    return [
        *messages,
        {"role": "user", "content": json.dumps(repair_payload, ensure_ascii=True)},
    ]


def _should_retry_visible_answer(exc: KnowledgeAnswerComposerError) -> bool:
    reason = str(exc)
    return reason.startswith(
        (
            "unsafe_answer_markdown",
            "unsafe_material_suitability",
            "requested_subject_",
            "material_overview_too_shallow",
            "material_comparison_too_shallow",
            "material_comparison_too_broad",
        )
    )


def parse_knowledge_answer_composer_output(
    raw_content: Any,
) -> KnowledgeAnswerComposerOutput:
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
    if requested and requested not in extract_material_ids(
        request.deterministic_answer
    ):
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
    if not _explicitly_requests_short_answer(lowered):
        return False
    materials = set(extract_material_ids(text))
    return len(materials) == 1


def _is_broad_material_information_request(user_message: str) -> bool:
    text = str(user_message or "").strip()
    if not text:
        return False
    lowered = f" {text.casefold()} "
    if any(marker in lowered for marker in _COMPARISON_MARKERS):
        return False
    if _explicitly_requests_short_answer(lowered):
        return False
    if len(set(extract_material_ids(text))) != 1:
        return False
    return bool(
        re.search(
            r"\b(was\s+kannst\s+du|detailliert|details?|info(?:s|rmation(?:en)?)?|"
            r"erkl[aä]r(?:e|en)?|erz[aä]hl|über|ueber|mehr\s+zu)\b",
            lowered,
        )
    )


def _explicitly_requests_short_answer(lowered_text: str) -> bool:
    return bool(
        re.search(
            r"\b(kurz|kompakt|knapp|in\s+einem\s+satz|in\s+2\s+sätzen|in\s+zwei\s+sätzen)\b",
            lowered_text,
        )
    )


def enforce_material_overview_depth(
    request: KnowledgeAnswerComposerInput,
    output: KnowledgeAnswerComposerOutput,
) -> KnowledgeAnswerComposerOutput:
    requested = _single_requested_material(request)
    if not requested:
        return output
    if not _is_broad_material_information_request(request.user_message):
        return output

    answer = str(output.answer_markdown or "").strip()
    lowered = answer.casefold()
    topic_patterns = _material_overview_topic_patterns(requested)
    topic_hits = sum(1 for pattern in topic_patterns if re.search(pattern, lowered))
    min_length = 900 if requested == "PTFE" else 850
    min_hits = 5 if requested == "PTFE" else 6
    value_hits = _material_overview_value_hits(requested, lowered)
    min_value_hits = 7 if requested == "PTFE" else 0
    if len(answer) < min_length or topic_hits < min_hits or value_hits < min_value_hits:
        raise KnowledgeAnswerComposerError("material_overview_too_shallow")
    return output


def _material_overview_value_hits(material_id: str, lowered_answer: str) -> int:
    if material_id != "PTFE":
        return 0
    value_patterns = (
        r"327",
        r"260",
        r"2[,.]1",
        r"2[,.]14|2[,.]20",
        r"shore\s*d",
        r"mpa",
        r"0[,.]20|0[,.]25",
        r"10\^-?5|10\^-?17|10\^-?18",
        r"kv/mm",
        r"0[,.]0002",
        r"0[,.]06",
        r"wasseraufnahme",
    )
    return sum(1 for pattern in value_patterns if re.search(pattern, lowered_answer))


def enforce_material_comparison_depth(
    request: KnowledgeAnswerComposerInput,
    output: KnowledgeAnswerComposerOutput,
) -> KnowledgeAnswerComposerOutput:
    requested = _requested_materials(request)
    if len(requested) < 2:
        return output
    if not _is_contextual_material_comparison_request(request, requested):
        return output

    answer = str(output.answer_markdown or "").strip()
    lowered = answer.casefold()
    topic_patterns = (
        r"temperatur|°c|\bc\b",
        r"medium|medien|chem|öl|oel|wasser|dampf|fluid",
        r"härte|haerte|shore|compound|rezeptur|acn|vernetzung",
        r"dynamik|reibung|verschlei[ßs]|rwdr|o-ring|dicht",
        r"grenze|kritisch|limit|risiko|alterung|quellung",
        r"hersteller|datenblatt|freigabe|nachweis|kompatibilit",
        r"kosten|verfügbarkeit|verfuegbarkeit|wirtschaft",
    )
    topic_hits = sum(1 for pattern in topic_patterns if re.search(pattern, lowered))
    if len(answer) < 950 or topic_hits < 5:
        raise KnowledgeAnswerComposerError("material_comparison_too_shallow")
    if set(requested[:2]) == {"PTFE", "FKM"} and len(answer) > 2400:
        raise KnowledgeAnswerComposerError("material_comparison_too_broad")
    return output


def _material_overview_topic_patterns(material_id: str) -> tuple[str, ...]:
    generic = (
        r"temperatur|°c|\bc\b",
        r"medium|medien|chem|öl|oel|wasser|dampf|fluid",
        r"härte|haerte|shore|compound|rezeptur|vernetzung",
        r"dynamik|reibung|verschlei[ßs]|o-ring|rwdr|dichtung",
        r"grenze|kritisch|limit|alterung|quellung|druckverform",
        r"hersteller|datenblatt|freigabe|nachweis|kompatibilit",
    )
    if material_id == "PTFE":
        return (
            r"chem",
            r"temperatur",
            r"reibung|gleit",
            r"kaltfluss|kriech|creep",
            r"füllstoff|fuellstoff|compound",
            r"gegenlauf|rauheit|welle",
            r"anwendung|dichtungs",
            r"freigabe|hersteller|nachweis",
        )
    if material_id == "NBR":
        return (*generic, r"acn|acrylnitril|nitril", r"ozon|uv|witter")
    if material_id == "FFKM":
        return (
            *generic,
            r"perfluor|premium|kosten|lieferzeit",
            r"compression|druckverform",
        )
    return generic


def _is_contextual_material_comparison_request(
    request: KnowledgeAnswerComposerInput,
    requested: tuple[str, ...],
) -> bool:
    text = f" {str(request.user_message or '').casefold()} "
    if any(marker in text for marker in _COMPARISON_MARKERS):
        return True
    if len(set(extract_material_ids(request.user_message))) >= 2:
        return True
    deterministic = str(request.deterministic_answer or "")
    title = deterministic.splitlines()[0] if deterministic else ""
    return (
        all(material in title for material in requested[:2])
        and "vergleich" in title.casefold()
    )


def enforce_requested_subject_fidelity(
    request: KnowledgeAnswerComposerInput,
    output: KnowledgeAnswerComposerOutput,
) -> KnowledgeAnswerComposerOutput:
    """Reject visible answers that drift away from the latest requested material."""

    requested_materials = _requested_materials(request)
    if not requested_materials:
        return output

    answer = str(output.answer_markdown or "")
    answer_materials = extract_material_ids(answer)
    if len(requested_materials) >= 2:
        missing = [
            material
            for material in requested_materials
            if material not in answer_materials
            and material.casefold() not in answer.casefold()
        ]
        if missing:
            raise KnowledgeAnswerComposerError(
                f"requested_subject_missing:{','.join(missing)}"
            )

        heading_materials = _first_heading_materials(answer)
        if heading_materials:
            expected_heading = requested_materials[: len(heading_materials)]
            if heading_materials[: len(expected_heading)] != expected_heading:
                raise KnowledgeAnswerComposerError("requested_subject_drift")
            unexpected_heading = [
                material
                for material in heading_materials
                if material not in requested_materials
            ]
            if unexpected_heading:
                raise KnowledgeAnswerComposerError("requested_subject_drift")

        first_materials = extract_material_ids(answer[:700])
        if first_materials and first_materials[0] != requested_materials[0]:
            raise KnowledgeAnswerComposerError("requested_subject_drift")
        if len(first_materials) >= 2 and first_materials[:2] != requested_materials[:2]:
            raise KnowledgeAnswerComposerError("requested_subject_drift")

        _reject_unscoped_material_suitability_claim(answer)
        return output

    requested = requested_materials[0]
    if (
        requested not in answer_materials
        and requested.casefold() not in answer.casefold()
    ):
        raise KnowledgeAnswerComposerError("requested_subject_missing")

    first_materials = extract_material_ids(answer[:500])
    if first_materials and first_materials[0] != requested:
        raise KnowledgeAnswerComposerError("requested_subject_drift")

    _reject_unscoped_material_suitability_claim(answer)

    return output


def _single_requested_material(request: KnowledgeAnswerComposerInput) -> str | None:
    requested = _requested_materials(request)
    if len(requested) == 1:
        return requested[0]
    return None


def _requested_materials(request: KnowledgeAnswerComposerInput) -> tuple[str, ...]:
    requested = tuple(
        str(material).strip().upper()
        for material in (getattr(request.context, "requested_subjects", ()) or ())
        if str(material or "").strip()
    )
    known = set(supported_material_ids())
    requested = tuple(material for material in requested if material in known)
    if requested:
        return _unique_materials(requested)
    return _unique_materials(extract_material_ids(request.user_message))


def _unique_materials(materials: tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for material in materials:
        if material not in seen:
            seen.append(material)
    return tuple(seen)


def _first_heading_materials(answer_markdown: str) -> tuple[str, ...]:
    for raw_line in str(answer_markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return extract_material_ids(line)
        if len(line) <= 160:
            return extract_material_ids(line)
        return ()
    return ()


_MATERIAL_CLAIM_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(material_id) for material_id in supported_material_ids())
    + r")\b[^.\n]{0,180}\b(?:ist\s+(?:gut\s+)?geeignet|geeignet\s+ist)\b",
    re.IGNORECASE | re.UNICODE,
)
_UNSCOPED_SUITABILITY_LABEL_RE = re.compile(
    r"\b(?:gute|sehr\s+gute|breite|klare|typische)\s+eignung\s+für\b",
    re.IGNORECASE | re.UNICODE,
)


def _reject_unscoped_material_suitability_claim(answer_markdown: str) -> None:
    answer = str(answer_markdown or "")
    for match in _MATERIAL_CLAIM_RE.finditer(answer):
        window = answer[max(0, match.start() - 60) : match.end()].casefold()
        if "nicht geeignet" in window or "nicht automatisch geeignet" in window:
            continue
        raise KnowledgeAnswerComposerError("unsafe_material_suitability_claim")
    for match in _UNSCOPED_SUITABILITY_LABEL_RE.finditer(answer):
        window = answer[max(0, match.start() - 40) : match.end()].casefold()
        if "keine" in window or "nicht" in window:
            continue
        raise KnowledgeAnswerComposerError("unsafe_material_suitability_label")


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
        "Für eine konkrete Einschätzung brauche ich Medium, Temperatur und "
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
    match = re.search(
        r"\bTypische Orientierung:\s*(?P<section>.*)", text, flags=re.DOTALL
    )
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
    return prompts.render(
        "knowledge/answer_composer.j2",
        {"prompt_version": KNOWLEDGE_ANSWER_COMPOSER_PROMPT_VERSION},
    )


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
