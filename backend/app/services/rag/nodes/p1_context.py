"""P1 Context Node for SEALAI v4.4.0 (Sprint 4).

Migrates WorkingProfile extraction from frontdoor_discovery_node /
supervisor_policy_node into a dedicated, clearly bounded node.

Responsibilities:
- Extract WorkingProfile fields from user messages via LLM structured output
- Support two modes via router_classification:
    new_case   → emits fresh WorkingProfile patch
    follow_up  → emits partial WorkingProfile patch for reducer merge
- No RAG, no material/type research (those are P2/P3)
- Tolerates LLM failure gracefully (keeps existing profile, sets error hint)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from langgraph.types import Command

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.messages import (
    flatten_message_content,
    latest_user_text,
    sanitize_message_history,
)
from app.langgraph_v2.utils.parameter_patch import stage_extracted_parameter_patch
from app.langgraph_v2.utils.jinja import render_template
from app.services.rag.state import WorkingProfile
from app.langgraph_v2.nodes.persona_detection import update_persona_in_state

logger = structlog.get_logger("rag.nodes.p1_context")

_SEAL_MATERIAL_TOKENS = frozenset(
    {
        "ptfe",
        "nbr",
        "hnbr",
        "fkm",
        "ffkm",
        "epdm",
        "vmq",
        "fvmq",
        "pu",
        "pur",
        "tpu",
        "peek",
        "elastomer",
        "elastomeric",
    }
)
_OPTION_A_PATTERN = re.compile(r"\boption\s*a\b", re.IGNORECASE)
_OPTION_B_PATTERN = re.compile(r"\boption\s*b\b", re.IGNORECASE)
_OPTION_SELECTION_MARKERS = (
    "wir nehmen",
    "ich nehme",
    "nehmen wir",
    "nehme ich",
    "wir waehlen",
    "ich waehle",
    "wir wählen",
    "ich wähle",
    "entscheide",
    "entscheidung",
    "akzept",
    "passt",
    "einverstanden",
    "go with",
    "choose",
    "chosen",
)
_HRC_PATTERN = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*hrc\b", re.IGNORECASE)
_OPTION_BLOCK_PATTERN = r"(?is)(option\s*{letter}\b.*?)(?=option\s*[a-z]\b|$)"
_MIN_ACCEPTED_HRC = 58.0


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().replace(",", ".")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _normalize_material_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text)


def _looks_like_seal_material(value: Any) -> bool:
    token = _normalize_material_token(value)
    if not token:
        return False
    return token in _SEAL_MATERIAL_TOKENS

# ---------------------------------------------------------------------------
# Extraction schema (lenient — accepts nulls freely)
# ---------------------------------------------------------------------------


class _P1Extraction(BaseModel):
    """LLM output schema for P1 WorkingProfile extraction."""

    medium: Optional[str] = None
    medium_detail: Optional[str] = None
    pressure_max_bar: Optional[float] = None
    pressure_min_bar: Optional[float] = None
    temperature_max_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    flange_standard: Optional[str] = None
    flange_dn: Optional[int] = None
    flange_pn: Optional[int] = None
    flange_class: Optional[int] = None
    bolt_count: Optional[int] = None
    bolt_size: Optional[str] = None
    cyclic_load: Optional[bool] = None
    emission_class: Optional[str] = None
    industry_sector: Optional[str] = None
    material: Optional[str] = Field(
        default=None,
        description=(
            "The material of the shaft/counter-surface (e.g., steel, stainless steel, 1.4404). "
            "STRICT RULE: NEVER extract the seal material (e.g., PTFE, elastomer) into this field. "
            "This is ONLY for the hardware/shaft."
        ),
    )
    seal_material: Optional[str] = None
    product_name: Optional[str] = None
    shaft_d1_mm: Optional[float] = None
    shaft_diameter: Optional[float] = None
    rpm: Optional[float] = None
    speed_rpm: Optional[float] = None
    n: Optional[float] = None
    d1: Optional[float] = None
    elastomer_material: Optional[str] = None
    hrc_value: Optional[float] = None
    clearance_gap_mm: Optional[float] = None

    model_config = ConfigDict(extra="ignore")



# ---------------------------------------------------------------------------
# LLM extraction helpers
# ---------------------------------------------------------------------------


def _build_messages(user_text: str, history: List[Any]) -> List[BaseMessage]:
    """Build a sanitized LLM message list from user text and prior history."""
    system_prompt = render_template(
        "p1_context_extractor.j2",
        {"include_resume_rules": True},
    )
    msgs: List[BaseMessage] = [SystemMessage(content=system_prompt)]
    sanitized_history = sanitize_message_history(history, include_system=False)

    # Include at most the last 4 history messages for context (avoid token bloat)
    msgs.extend(sanitized_history[-4:])

    text = user_text.strip()
    if text:
        last_msg = sanitized_history[-1] if sanitized_history else None
        last_is_same_user = isinstance(last_msg, HumanMessage) and (
            flatten_message_content(getattr(last_msg, "content", "")).strip() == text
        )
        if not last_is_same_user:
            msgs.append(HumanMessage(content=text))
    return msgs


def _message_to_text(msg: Any) -> str:
    return flatten_message_content(getattr(msg, "content", ""))


def _latest_assistant_text(history: List[Any]) -> str:
    for msg in reversed(sanitize_message_history(history, include_system=False)):
        if isinstance(msg, AIMessage):
            return _message_to_text(msg).strip()
    return ""


def _is_active_resume_session(state: SealAIState) -> bool:
    classification = str(state.conversation.router_classification or "").strip().lower()
    if classification == "resume":
        return True
    if bool(state.system.awaiting_user_confirmation):
        return True
    if bool((state.system.pending_action or "").strip()):
        return True
    return bool(state.reasoning.qgate_has_blockers)


def _detect_selected_option(user_text: str) -> str:
    text = (user_text or "").strip().lower()
    if not text:
        return ""
    selected = ""
    if _OPTION_A_PATTERN.search(text):
        selected = "a"
    elif _OPTION_B_PATTERN.search(text):
        selected = "b"
    if not selected:
        return ""
    if any(marker in text for marker in _OPTION_SELECTION_MARKERS):
        return selected
    if text.startswith(f"option {selected}"):
        return selected
    return ""


def _extract_option_block(text: str, option_letter: str) -> str:
    if not text or option_letter not in {"a", "b"}:
        return ""
    match = re.search(_OPTION_BLOCK_PATTERN.format(letter=option_letter), text, re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _extract_hrc_value(*texts: str) -> Optional[float]:
    for text in texts:
        if not text:
            continue
        match = _HRC_PATTERN.search(text)
        if not match:
            continue
        value = _to_float_or_none(match.group(1))
        if value is not None:
            return value
    return None


def _derive_resume_overrides(state: SealAIState, user_text: str, history: List[Any]) -> Dict[str, Any]:
    if not _is_active_resume_session(state):
        return {}
    selected_option = _detect_selected_option(user_text)
    if not selected_option:
        return {}

    assistant_text = _latest_assistant_text(history)
    selected_block = _extract_option_block(assistant_text, selected_option)
    hrc_value = _extract_hrc_value(user_text, selected_block, assistant_text)

    # Option-A fallback for hardness blockers when no explicit HRC number is repeated.
    if hrc_value is None and selected_option == "a":
        lower_ctx = f"{user_text}\n{selected_block}\n{assistant_text}".lower()
        mentions_hardness = any(token in lower_ctx for token in ("hrc", "härte", "haerte", "harden", "haerten"))
        if mentions_hardness:
            hrc_value = _MIN_ACCEPTED_HRC

    if hrc_value is None:
        return {}
    return {"hrc_value": hrc_value}


def _invoke_extraction(user_text: str, history: List[Any]) -> _P1Extraction:
    """Call the LLM and return a validated _P1Extraction."""
    model_name = os.getenv("OPENAI_MODEL_MINI", "gpt-4.1-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.0, max_retries=2)
    structured = llm.with_structured_output(_P1Extraction, method="json_schema", strict=True)
    result = structured.invoke(_build_messages(user_text, history))
    if isinstance(result, _P1Extraction):
        return result
    return _P1Extraction.model_validate(result)


# ---------------------------------------------------------------------------
# Profile merging
# ---------------------------------------------------------------------------


def _merge_extraction_into_profile(
    existing: Optional[WorkingProfile],
    extracted: _P1Extraction,
) -> WorkingProfile:
    """Compatibility helper for tests; production flow now uses reducer patches."""
    base: Dict[str, Any] = existing.model_dump(exclude_none=True) if existing else {}
    profile_fields = set(getattr(WorkingProfile, "model_fields", {}).keys())
    for field_name, value in extracted.model_dump().items():
        if field_name == "material" and _looks_like_seal_material(value):
            # Protect shaft/counterface material from seal-material cross-talk.
            continue
        if value is not None and field_name in profile_fields:
            base[field_name] = value

    # Pydantic validates cross-field consistency (min ≤ max, bolt_count even, etc.)
    try:
        return WorkingProfile.model_validate(base)
    except ValidationError as exc:
        # If merged data violates constraints (e.g. follow-up reverses min/max),
        # fall back to only the extraction result — never silently corrupt the profile.
        logger.warning(
            "p1_context_merge_validation_error",
            error=str(exc),
            base_keys=list(base.keys()),
        )
        try:
            return WorkingProfile.model_validate(extracted.model_dump(exclude_none=True))
        except ValidationError:
            return existing or WorkingProfile()


def _deep_merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        left_value = merged.get(key)
        if isinstance(left_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(left_value, value)
        else:
            merged[key] = value
    return merged


def _build_working_profile_patch(extracted: _P1Extraction) -> WorkingProfile:
    """Build partial WorkingProfile patch; reducer handles merge with state."""
    payload = extracted.model_dump(exclude_none=True)
    if _looks_like_seal_material(payload.get("material")):
        raw = str(payload.get("material") or "").strip()
        payload.pop("material", None)
        if raw:
            payload.setdefault("seal_material", raw)
    return WorkingProfile.model_validate(payload)


def _merge_extraction_into_extracted_params(
    existing: Optional[Dict[str, Any]],
    extracted: _P1Extraction,
) -> Dict[str, Any]:
    """Merge P1 extraction into working_profile.extracted_params with physics-friendly aliases."""
    merged: Dict[str, Any] = dict(existing or {})
    payload = extracted.model_dump(exclude_none=True)

    numeric_fields = {
        "pressure_max_bar",
        "pressure_min_bar",
        "temperature_max_c",
        "temperature_min_c",
        "rpm",
        "speed_rpm",
        "n",
        "shaft_d1_mm",
        "shaft_diameter",
        "d1",
        "hrc_value",
        "clearance_gap_mm",
    }

    # Generic deep merge keeps prior values and only overlays new non-null fields.
    # Skip numeric fields (handled with normalization below).
    generic_payload: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in numeric_fields:
            continue
        if key == "material" and _looks_like_seal_material(value):
            # Prevent seal-material spillover into shaft/counterface material.
            continue
        generic_payload[key] = value
    if generic_payload:
        merged = _deep_merge_dicts(merged, generic_payload)

    # Numeric values that downstream deterministic nodes consume.
    for key in numeric_fields:
        if key in payload:
            numeric_value = _to_float_or_none(payload.get(key))
            if numeric_value is not None:
                merged[key] = numeric_value

    # Diameter aliases for robust lookup in node_p4_live_calc.
    shaft_d1_mm = (
        _to_float_or_none(payload.get("shaft_d1_mm"))
        or _to_float_or_none(payload.get("shaft_diameter"))
        or _to_float_or_none(payload.get("d1"))
    )
    if shaft_d1_mm is not None:
        merged["shaft_d1_mm"] = shaft_d1_mm
        merged["shaft_d1"] = shaft_d1_mm
        merged["d1"] = shaft_d1_mm

    # Speed aliases for robust lookup across legacy and v2 nodes.
    rpm_value = (
        _to_float_or_none(payload.get("rpm"))
        or _to_float_or_none(payload.get("speed_rpm"))
        or _to_float_or_none(payload.get("n"))
    )
    if rpm_value is not None:
        merged["rpm"] = rpm_value
        merged["speed_rpm"] = rpm_value
        merged["n"] = rpm_value

    # Hardness alias for existing consumers that read "hrc".
    if "hrc_value" in merged:
        merged["hrc"] = merged["hrc_value"]

    # Keep selected seal material explicitly separate from shaft material.
    seal_material = payload.get("seal_material")
    if isinstance(seal_material, str) and seal_material.strip():
        merged["seal_material"] = seal_material.strip()

    # If the model still emitted a seal token in `material`, remap it safely.
    raw_material = payload.get("material")
    if _looks_like_seal_material(raw_material):
        text = str(raw_material or "").strip()
        if text:
            merged.setdefault("seal_material", text)
            if str(merged.get("material") or "").strip().lower() == text.lower():
                merged.pop("material", None)

    return merged


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def _resolve_intent_route(state: SealAIState) -> str:
    raw_intent = getattr(state.conversation, "intent", None)
    if isinstance(raw_intent, str):
        normalized = re.sub(r"[^a-z0-9]+", "_", raw_intent.strip().lower()).strip("_")
        if normalized in {"smalltalk", "chit_chat", "chitchat", "greeting"}:
            return "smalltalk"
        return "engineering"

    goal = str(getattr(raw_intent, "goal", "") or "").strip().lower()
    routing_hint = str(getattr(raw_intent, "routing_hint", "") or "").strip().lower()
    if goal == "smalltalk" or routing_hint in {"smalltalk", "chit_chat"}:
        return "smalltalk"
    return "engineering"


def node_p1_context(state: SealAIState, *_args: Any, **_kwargs: Any) -> Command:
    """P1 Context Node — extract/update WorkingProfile from user messages.

    Wired after node_router for 'new_case' and 'follow_up' paths.
    Routes to deterministic engineering extraction only when intent is engineering.
    Emits WorkingProfile PATCH objects; reducer merges them into canonical state.
    Does NOT touch RAG retrieval, material research, or intent classification.
    """
    history = sanitize_message_history(state.conversation.messages, include_system=False)
    user_text = (latest_user_text(state.conversation.messages) or latest_user_text(history) or "").strip()
    classification = state.conversation.router_classification or "new_case"
    is_new_case = str(classification).strip().lower() == "new_case"
    # Hard reset for new cases: never bleed prior thread/profile state into a
    # fresh extraction turn.
    existing_profile = None if is_new_case else state.working_profile.engineering_profile
    existing_extracted_params = {} if is_new_case else dict(state.working_profile.extracted_params or {})

    logger.info(
        "p1_context_start",
        classification=classification,
        has_existing_profile=bool(existing_profile),
        user_text_len=len(user_text),
        run_id=state.system.run_id,
        thread_id=state.conversation.thread_id,
    )

    extracted: Optional[_P1Extraction] = None
    error_hint: Optional[str] = None

    try:
        extracted = _invoke_extraction(user_text, history)
    except Exception as exc:
        error_hint = f"p1_extraction_failed: {exc}"
        logger.warning(
            "p1_context_llm_failed",
            error=str(exc),
            classification=classification,
            run_id=state.system.run_id,
        )

    resume_overrides = _derive_resume_overrides(state, user_text, history)
    if resume_overrides:
        extracted = (
            extracted.model_copy(update=resume_overrides)
            if extracted is not None
            else _P1Extraction.model_validate(resume_overrides)
        )
        logger.info(
            "p1_context_resume_overrides_applied",
            overrides=resume_overrides,
            classification=classification,
            run_id=state.system.run_id,
        )

    profile_patch: Optional[WorkingProfile] = None
    merged_profile = existing_profile or WorkingProfile()
    if extracted is not None:
        try:
            profile_patch = _build_working_profile_patch(extracted)
        except ValidationError as exc:
            error_hint = error_hint or f"p1_profile_patch_invalid: {exc}"
            logger.warning(
                "p1_context_profile_patch_invalid",
                error=str(exc),
                run_id=state.system.run_id,
            )
        merged_profile = _merge_extraction_into_profile(existing_profile, extracted)

    effective_profile = merged_profile
    coverage = effective_profile.coverage_ratio()

    logger.info(
        "p1_context_done",
        classification=classification,
        profile_coverage=round(coverage, 3),
        profile_patch_fields=list((profile_patch.model_dump(exclude_none=True) if profile_patch else {}).keys()),
        extracted_fields=(
            [k for k, v in extracted.model_dump().items() if v is not None]
            if extracted
            else []
        ),
        run_id=state.system.run_id,
    )

    merged_extracted_params = dict(existing_extracted_params)
    merged_extracted_provenance = dict(state.reasoning.extracted_parameter_provenance or {})
    merged_extracted_identity = dict(state.reasoning.extracted_parameter_identity or {})
    if extracted is not None:
        extracted_patch = _merge_extraction_into_extracted_params({}, extracted)
        (
            merged_extracted_params,
            merged_extracted_provenance,
            merged_extracted_identity,
            _applied_candidate_fields,
        ) = stage_extracted_parameter_patch(
            merged_extracted_params,
            extracted_patch,
            merged_extracted_provenance,
            merged_extracted_identity,
            source="p1_context_extracted",
        )

    working_profile_update: Dict[str, Any] = {"extracted_params": merged_extracted_params}
    if is_new_case:
        working_profile_update["engineering_profile"] = WorkingProfile()

    result: Dict[str, Any] = {
        "working_profile": working_profile_update,
        "reasoning": {
            "phase": PHASE.FRONTDOOR,  # reuse existing FRONTDOOR phase; P1 is pre-frontdoor in v4
            "last_node": "node_p1_context",
            "turn_count": int(state.reasoning.turn_count or 0) + 1,
            "extracted_parameter_provenance": merged_extracted_provenance,
            "extracted_parameter_identity": merged_extracted_identity,
        },
    }
    persona_patch = update_persona_in_state(state)
    result.update(persona_patch)

    if error_hint:
        result.setdefault("system", {})
        result["system"]["error"] = error_hint

    intent_route = _resolve_intent_route(state)
    if intent_route == "smalltalk":
        logger.info(
            "p1_context_smalltalk_bypass_engineering",
            classification=classification,
            run_id=state.system.run_id,
            thread_id=state.conversation.thread_id,
        )
        return Command(
            update=result,
            goto="response_node",
        )

    if bool((state.reasoning.flags or {}).get("use_reasoning_core_r3")):
        return Command(
            update=result,
            goto="combinatorial_chemistry_guard_node",
        )

    return Command(
        update=result,
    )


__all__ = [
    "node_p1_context",
    "_merge_extraction_into_profile",
    "_P1Extraction",
]
