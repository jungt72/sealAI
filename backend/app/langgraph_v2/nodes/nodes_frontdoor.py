from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import (
    Intent,
    RenderedPrompt,
    SealAIExtractedParameters,
    SealAIIntentOutput,
    SealAIState,
    TechnicalParameters,
    WorkingMemory,
)
from app.langgraph_v2.utils.llm_factory import get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.langgraph_v2.nodes.persona_detection import update_persona_in_state
from app.utils.jinja_renderer import render_and_hash

logger = structlog.get_logger("langgraph_v2.nodes_frontdoor")

_MATERIAL_OR_TRADE_MARKERS = (
    "datenblatt",
    "datasheet",
    "data sheet",
    "technical sheet",
    "werkstoff",
    "material",
    "trade_name",
    "trade name",
    "produkt",
    "product",
    "polymer",
    "elastomer",
    "nbr",
    "fkm",
    "epdm",
    "hnbr",
    "ptfe",
    "vmq",
    "ffkm",
    "kyrolon",
    "qdrant",
    "search_technical_docs",
    "get_available_filters",
)
_MATERIAL_CODE_PATTERN = re.compile(r"\b[a-z]{2,6}[-_/]?\d{2,4}\b", re.IGNORECASE)
_TRADE_NAME_EXPLICIT_PATTERN = re.compile(
    r"\btrade[_\s-]?name\s*[:=]?\s*[\"']?([a-z0-9][a-z0-9 _./-]{1,120})[\"']?",
    re.IGNORECASE,
)
_TRADE_NAME_QUERY_PATTERNS = (
    re.compile(
        r"\b(?:ueber|uber|ube|uebe|über|übe|about|zu|for)\s+([a-z0-9][a-z0-9._/-]{2,})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:was\s+ist|what\s+is|infos?\s+zu|informationen?\s+zu|tell\s+me\s+about)\s+([a-z0-9][a-z0-9._/-]{2,})\b",
        re.IGNORECASE,
    ),
    re.compile(r"[\"']([a-z0-9][a-z0-9 _./-]{2,})[\"']", re.IGNORECASE),
)
_GENERIC_TRADE_STOPWORDS = frozenset(
    {
        "das",
        "die",
        "der",
        "ein",
        "eine",
        "einem",
        "einer",
        "ich",
        "du",
        "mir",
        "dir",
        "und",
        "oder",
        "ist",
        "sind",
        "sagen",
        "wissen",
        "mehr",
        "dazu",
        "darueber",
        "darüber",
        "about",
        "what",
        "this",
        "that",
    }
)

_FRONTDOOR_SYSTEM_TEMPLATE = "frontdoor_system_v2.j2"
_FRONTDOOR_SYSTEM_TEMPLATE_VERSION = "2.0.0"
_FRONTDOOR_MAX_HISTORY_TURNS = 2

_TECHNICAL_CUE_TERMS = [
    "PTFE",
    "bar",
    "psi",
    "°C",
    "mm",
    "FKM",
    "NBR",
    "Kyrolon",
    "datasheet",
    "datenblatt",
    "preis",
    "price",
]

_INTENT_TO_GOAL: Dict[str, str] = {
    "CHIT_CHAT": "smalltalk",
    "GENERAL_KNOWLEDGE": "explanation_or_comparison",
    "MATERIAL_RESEARCH": "explanation_or_comparison",
    "COMMERCIAL": "design_recommendation",
    "ENGINEERING_CALCULATION": "design_recommendation",
}

_TASK_INTENT_TO_CATEGORY: Dict[str, str] = {
    "smalltalk": "CHIT_CHAT",
    "general_knowledge": "GENERAL_KNOWLEDGE",
    "material_research": "MATERIAL_RESEARCH",
    "commercial": "COMMERCIAL",
    "engineering_calculation": "ENGINEERING_CALCULATION",
    "design_recommendation": "ENGINEERING_CALCULATION",
    "troubleshooting_leakage": "ENGINEERING_CALCULATION",
    "out_of_scope": "GENERAL_KNOWLEDGE",
}

_TASK_INTENT_ALIASES: Dict[str, str] = {
    "chit_chat": "smalltalk",
    "chitchat": "smalltalk",
    "social": "smalltalk",
    "greeting": "smalltalk",
    "material": "material_research",
    "materials": "material_research",
    "research": "material_research",
    "retrieval": "material_research",
    "rag": "material_research",
    "commercial_request": "commercial",
    "pricing": "commercial",
    "price": "commercial",
    "quote": "commercial",
    "rfq": "commercial",
    "engineering": "engineering_calculation",
    "calculation": "engineering_calculation",
    "calc": "engineering_calculation",
    "design": "design_recommendation",
    "explanation": "general_knowledge",
    "comparison": "general_knowledge",
}


class FrontdoorRouteAxesOutput(BaseModel):
    social_opening: bool = False
    task_intents: list[str] = Field(default_factory=list)
    is_safety_critical: bool = False
    requires_rag: bool = False
    needs_pricing: bool = False
    extracted_parameters: SealAIExtractedParameters = Field(default_factory=SealAIExtractedParameters)
    reasoning: str = ""

    model_config = ConfigDict(extra="forbid")


def _sanitize_trade_candidate(value: str) -> Optional[str]:
    cleaned = re.sub(r"[^\w\s./-]", "", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    token = cleaned.lower()
    if token in _GENERIC_TRADE_STOPWORDS:
        return None
    if len(token) < 3:
        return None
    return cleaned


def extract_trade_name_candidate(text: Optional[str]) -> Optional[str]:
    source = (text or "").strip()
    if not source:
        return None
    explicit = _TRADE_NAME_EXPLICIT_PATTERN.search(source)
    if explicit:
        candidate = _sanitize_trade_candidate(explicit.group(1))
        if candidate:
            return candidate
    for pattern in _TRADE_NAME_QUERY_PATTERNS:
        match = pattern.search(source)
        if not match:
            continue
        candidate = _sanitize_trade_candidate(match.group(1))
        if candidate:
            return candidate
    return None


def detect_material_or_trade_query(text: Optional[str]) -> bool:
    source = (text or "").strip()
    if not source:
        return False
    normalized = re.sub(r"[^\wäöüÄÖÜß\s/_\\.-]", " ", source).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return False
    if any(marker in normalized for marker in _MATERIAL_OR_TRADE_MARKERS):
        return True
    if _MATERIAL_CODE_PATTERN.search(normalized):
        return True
    return bool(extract_trade_name_candidate(source))


def detect_sources_request(text: Optional[str]) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"[^\wäöüÄÖÜß\s]", " ", text).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return False

    negation_patterns = [
        r"\bohne\s+(?:irgend\w+\s+)?(?:quellen?|quelle|wissensdatenbank|datenbank|normen?)\b",
        r"\bkeine\s+(?:quellen?|quelle|wissensdatenbank|datenbank|normen?)\b",
        r"\bnicht\s+(?:mit|unter)\s+(?:quellen?|quelle|wissensdatenbank|datenbank|normen?)\b",
        r"\bohne\s+(?:din|en|iso|astm|vdi)\b",
        r"\bkeine\s+(?:din|en|iso|astm|vdi)\b",
    ]
    if any(re.search(pat, cleaned) for pat in negation_patterns):
        return False

    patterns = [
        r"\bmit quellen\b",
        r"\bquelle\b",
        r"\bquellen\b",
        r"\bwissensdatenbank\b",
        r"\bwissens database\b",
        r"\bnorm\b",
        r"\bnormen\b",
        r"\b(din|en|iso|astm|vdi)\b",
    ]
    return any(re.search(pat, cleaned) for pat in patterns)


def _normalize_task_intent(task_intent: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (task_intent or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return _TASK_INTENT_ALIASES.get(normalized, normalized)


def _normalize_task_intents(task_intents: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for intent in task_intents:
        canonical = _normalize_task_intent(intent)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return normalized


def _legacy_category_to_task_intents(intent_category: str) -> list[str]:
    mapping: Dict[str, list[str]] = {
        "CHIT_CHAT": [],
        "GENERAL_KNOWLEDGE": ["general_knowledge"],
        "MATERIAL_RESEARCH": ["material_research"],
        "COMMERCIAL": ["commercial"],
        "ENGINEERING_CALCULATION": ["engineering_calculation"],
    }
    return mapping.get((intent_category or "").strip().upper(), ["engineering_calculation"])


def _category_from_task_intents(task_intents: list[str], social_opening: bool) -> str:
    if task_intents:
        for intent in task_intents:
            category = _TASK_INTENT_TO_CATEGORY.get(intent)
            if category:
                return category
        return "ENGINEERING_CALCULATION"
    if social_opening:
        return "CHIT_CHAT"
    return "ENGINEERING_CALCULATION"


def _compile_technical_cue_pattern(term: str) -> re.Pattern[str]:
    if term == "°C":
        return re.compile(r"°\s*c", re.IGNORECASE)
    if term == "mm":
        return re.compile(r"\b\d+(?:[.,]\d+)?\s*mm\b|\bmm\b", re.IGNORECASE)
    return re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)


_TECHNICAL_CUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (term, _compile_technical_cue_pattern(term)) for term in _TECHNICAL_CUE_TERMS
)


def _detect_technical_cue_matches(text: str) -> list[str]:
    source = text or ""
    return [term for term, pattern in _TECHNICAL_CUE_PATTERNS if pattern.search(source)]


def _coerce_frontdoor_output(raw: Any) -> FrontdoorRouteAxesOutput:
    if isinstance(raw, FrontdoorRouteAxesOutput):
        return raw
    if isinstance(raw, SealAIIntentOutput):
        return FrontdoorRouteAxesOutput(
            social_opening=(raw.intent_category == "CHIT_CHAT"),
            task_intents=_legacy_category_to_task_intents(raw.intent_category),
            is_safety_critical=raw.is_safety_critical,
            requires_rag=raw.requires_rag,
            needs_pricing=raw.needs_pricing,
            extracted_parameters=raw.extracted_parameters,
            reasoning=raw.reasoning,
        )
    return FrontdoorRouteAxesOutput.model_validate(raw)


def _truncate_messages_to_last_turns(messages: list[Any], max_turns: int = 2) -> list[Any]:
    if max_turns <= 0 or not messages:
        return []
    human_turns_seen = 0
    start_index = 0
    for idx in range(len(messages) - 1, -1, -1):
        if isinstance(messages[idx], HumanMessage):
            human_turns_seen += 1
            if human_turns_seen == max_turns:
                start_index = idx
                break
    return messages[start_index:]


def _get_working_memory(state: SealAIState, updates: Dict[str, Any]) -> WorkingMemory:
    wm = state.working_memory or WorkingMemory()
    return wm.model_copy(update=updates)


def _render_frontdoor_prompt_trace(state: SealAIState) -> RenderedPrompt:
    return render_and_hash(
        template_path=_FRONTDOOR_SYSTEM_TEMPLATE,
        context={"state": state.model_dump(exclude_none=False)},
        version=_FRONTDOOR_SYSTEM_TEMPLATE_VERSION,
    )


def _build_frontdoor_messages(state: SealAIState, user_text: str) -> list[Any]:
    history = _truncate_messages_to_last_turns(list(state.messages or []), max_turns=_FRONTDOOR_MAX_HISTORY_TURNS)
    if not history and user_text.strip():
        history = [HumanMessage(content=user_text)]
    prompt_trace = _render_frontdoor_prompt_trace(state)
    return [SystemMessage(content=prompt_trace.rendered_text), *history]


def _invoke_frontdoor_structured(state: SealAIState, user_text: str) -> FrontdoorRouteAxesOutput:
    model_name = get_model_tier("mini")
    llm = ChatOpenAI(model=model_name, temperature=0.0, max_retries=2)
    structured_llm = llm.with_structured_output(
        FrontdoorRouteAxesOutput,
        method="json_schema",
        strict=True,
    )
    response = structured_llm.invoke(_build_frontdoor_messages(state, user_text))
    if isinstance(response, FrontdoorRouteAxesOutput):
        return response
    return FrontdoorRouteAxesOutput.model_validate(response)


def _intent_goal_from_category(category: str) -> Literal[
    "smalltalk",
    "design_recommendation",
    "explanation_or_comparison",
    "troubleshooting_leakage",
    "out_of_scope",
]:
    return _INTENT_TO_GOAL.get(category, "design_recommendation")  # type: ignore[return-value]


def _extract_parameter_patch(structured: FrontdoorRouteAxesOutput) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    extracted = structured.extracted_parameters
    if extracted.pressure_bar is not None:
        patch["pressure_bar"] = float(extracted.pressure_bar)
    if extracted.temperature_c is not None:
        patch["temperature_C"] = float(extracted.temperature_c)
    if extracted.medium:
        patch["medium"] = extracted.medium.strip()
    return patch


def frontdoor_discovery_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("frontdoor_discovery_node", state)
    user_text = latest_user_text(state.get("messages")) or ""
    parameters = state.parameters or TechnicalParameters()
    prompt_trace = _render_frontdoor_prompt_trace(state)

    try:
        structured = _coerce_frontdoor_output(_invoke_frontdoor_structured(state, user_text))
    except Exception as exc:
        logger.warning(
            "frontdoor_structured_output_failed",
            error=str(exc),
            user_text=user_text,
            run_id=state.run_id,
            thread_id=state.thread_id,
        )
        structured = FrontdoorRouteAxesOutput(
            social_opening=False,
            task_intents=["engineering_calculation"],
            is_safety_critical=False,
            requires_rag=False,
            needs_pricing=False,
            reasoning="The request is treated as an engineering intake fallback.",
        )

    task_intents = _normalize_task_intents(structured.task_intents)
    technical_cue_matches = _detect_technical_cue_matches(user_text)

    # Prioritize last human message if it's purely social without technical cues.
    # This prevents history-bias where LLM still tags "material_research"
    # for a simple "thank you" after a technical discussion.
    if structured.social_opening and not technical_cue_matches:
        task_intents = []
        intent_category = "CHIT_CHAT"
    else:
        intent_category = _category_from_task_intents(task_intents, structured.social_opening)

    intent_goal = _intent_goal_from_category(intent_category)
    frontdoor_bypass_supervisor = bool(structured.social_opening and not task_intents)
    technical_cue_veto = bool(technical_cue_matches)
    if technical_cue_veto:
        frontdoor_bypass_supervisor = False
        logger.info(
            "frontdoor_technical_cue_veto",
            matched_terms=technical_cue_matches,
            run_id=state.run_id,
            thread_id=state.thread_id,
        )

    requires_rag = bool(structured.requires_rag or intent_category == "MATERIAL_RESEARCH")
    if intent_category == "CHIT_CHAT" and not technical_cue_matches:
        requires_rag = False

    needs_pricing = bool(structured.needs_pricing or intent_category == "COMMERCIAL")

    intent = Intent(
        goal=intent_goal,
        confidence=1.0,
        high_impact_gaps=[],
        needs_sources=requires_rag,
        need_sources=requires_rag,
        routing_hint=intent_category,
    )

    extracted_patch = _extract_parameter_patch(structured)
    merged_provenance = state.parameter_provenance
    if extracted_patch:
        merged_params, merged_provenance = apply_parameter_patch_with_provenance(
            parameters.as_dict(),
            extracted_patch,
            state.parameter_provenance,
            source="user",
        )
        parameters = TechnicalParameters.model_validate(merged_params)

    flags = dict(state.flags or {})
    flags.update(
        {
            "frontdoor_bypass_supervisor": frontdoor_bypass_supervisor,
            "frontdoor_social_opening": structured.social_opening,
            "frontdoor_task_intents": task_intents,
            "frontdoor_technical_cue_veto": technical_cue_veto,
            "frontdoor_technical_cue_matches": technical_cue_matches,
            "is_safety_critical": structured.is_safety_critical,
            "needs_pricing": needs_pricing,
            "frontdoor_intent_category": intent_category,
        }
    )

    wm_updates = {
        "frontdoor_reply": structured.reasoning,
        "design_notes": {
            **dict((state.working_memory or WorkingMemory()).design_notes or {}),
            "frontdoor_reasoning": structured.reasoning,
            "requested_quantity": structured.extracted_parameters.quantity,
            "requested_sku": structured.extracted_parameters.sku,
        },
    }
    wm = _get_working_memory(state, wm_updates)

    logger.info(
        "frontdoor_structured_intent",
        social_opening=structured.social_opening,
        task_intents=task_intents,
        intent_category=intent_category,
        mapped_goal=intent_goal,
        safety_critical=structured.is_safety_critical,
        requires_rag=requires_rag,
        needs_pricing=needs_pricing,
        bypass_supervisor=frontdoor_bypass_supervisor,
        technical_cue_veto=technical_cue_veto,
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    persona_patch = update_persona_in_state(state)
    return {
        "intent": intent,
        "working_memory": wm,
        "prompt_traces": [prompt_trace],
        "phase": PHASE.FRONTDOOR,
        "last_node": "frontdoor_discovery_node",
        "parameters": parameters,
        "parameter_provenance": merged_provenance,
        "requires_rag": requires_rag,
        "need_sources": requires_rag,
        "flags": flags,
        **persona_patch,
    }


__all__ = [
    "frontdoor_discovery_node",
    "detect_sources_request",
    "detect_material_or_trade_query",
    "extract_trade_name_candidate",
    "FrontdoorRouteAxesOutput",
    "SealAIIntentOutput",
]
