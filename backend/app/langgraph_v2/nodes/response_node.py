"""Centralized response node for Supervisor-controlled user messages."""

from __future__ import annotations

import json
import os
from typing import Dict, Any

from langchain_core.messages import AIMessage

from app.core.config import settings
from app.langgraph_v2.constants import MODEL_MINI
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.assertion_cycle import stamp_patch_with_assertion_binding
from app.langgraph_v2.utils.jinja import render_prompt_sections, render_template
from app.langgraph_v2.utils.llm_factory import run_llm
from app.langgraph_v2.utils.messages import flatten_message_content

_ENGINEERING_INTENT_GOALS = {
    "engineering",
    "engineering_calculation",
    "design_recommendation",
    "troubleshooting_leakage",
}

_ENGINEERING_RESPONSE_KINDS = {
    "engineering",
    "kb_factcard",
    "consulting",
    "preflight_parameters",
    "material",
    "profile",
    "critical_review",
    "final",
}

_COMPLEXITY_HINTS = {"complex", "high", "advanced", "safety_critical", "critical"}
_FALSE_VALUES = {"0", "false", "off", "no"}
_FAKE_VALUES = {"1", "true", "yes", "on"}
_PARTIAL_EXPERT_FAILURE_ERROR = "partial_expert_failure"
_PARTIAL_EXPERT_FAILURE_WARNING = (
    "Ein Teil der Experten-Analyse ist fehlgeschlagen, bitte Ergebnisse kritisch pruefen."
)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def _has_runtime_llm() -> bool:
    fake_llm = str(os.getenv("LANGGRAPH_USE_FAKE_LLM", "") or "").strip().lower()
    if fake_llm in _FAKE_VALUES:
        return True

    key = str(getattr(settings, "openai_api_key", "") or "").strip()
    if not key:
        key = str(os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not key:
        return False

    lower_key = key.lower()
    if lower_key in {"test", "dummy", "placeholder", "changeme"}:
        return False
    if lower_key.startswith("test-"):
        return False
    return True


def _should_use_light_llm_summary(
    *,
    state: SealAIState,
    intent_goal: str,
    response_kind: str,
    calc_results: Dict[str, Any],
) -> bool:
    if not calc_results:
        return False
    if state.reasoning.ask_missing_request is not None:
        return False

    if str(os.getenv("SEALAI_ENABLE_LIGHT_RESPONSE_SUMMARY", "1")).strip().lower() in _FALSE_VALUES:
        return False

    if not _has_runtime_llm():
        return False

    flags = state.reasoning.flags or {}
    frontdoor_intent_category = str(flags.get("frontdoor_intent_category") or "").strip().upper()
    intent_goal_norm = str(intent_goal or "").strip().lower()
    response_kind_norm = str(response_kind or "").strip().lower()

    is_engineering = (
        intent_goal_norm in _ENGINEERING_INTENT_GOALS
        or response_kind_norm in _ENGINEERING_RESPONSE_KINDS
        or frontdoor_intent_category == "ENGINEERING_CALCULATION"
    )
    if not is_engineering:
        return False

    complexity_raw = ""
    intent_obj = state.conversation.intent
    if intent_obj is not None and not isinstance(intent_obj, str):
        complexity_raw = str(getattr(intent_obj, "complexity", "") or "")
    if not complexity_raw:
        complexity_raw = str(flags.get("frontdoor_complexity") or flags.get("complexity") or "")

    complexity_norm = complexity_raw.strip().lower()
    is_safety_critical = bool(flags.get("is_safety_critical"))
    return is_safety_critical or (complexity_norm in _COMPLEXITY_HINTS)


def _light_llm_summary(
    *,
    base_text: str,
    design_notes: Dict[str, Any],
    calc_results: Dict[str, Any],
) -> str | None:
    system_prompt, prompt = render_prompt_sections(
        "response_light_summary.j2",
        {
            "base_text": base_text.strip(),
            "design_notes_json": json.dumps(design_notes, ensure_ascii=False),
            "calc_results_json": json.dumps(calc_results, ensure_ascii=False),
        },
    )
    candidate = run_llm(
        model=MODEL_MINI,
        prompt=prompt,
        system=system_prompt,
        temperature=0.0,
        max_tokens=220,
    ).strip()
    if not candidate:
        return None
    if candidate.startswith("Entschuldigung, bei der internen Modellabfrage ist ein Fehler aufgetreten."):
        return None
    return candidate


def response_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, object]:
    """
    Single point that turns structured state into a user-facing message.

    Responsibility:
    - select appropriate template based on response_kind/ask_missing/knowledge/error
    - append exactly one AIMessage
    - set final_text
    """
    wm: WorkingMemory = state.reasoning.working_memory or WorkingMemory()
    ask_missing = state.reasoning.ask_missing_request
    phase = state.reasoning.phase or "final"
    latest_ai_text = ""
    for message in reversed(list(state.conversation.messages or [])):
        role = str(getattr(message, "type", "") or getattr(message, "role", "") or "").strip().lower()
        if role not in {"ai", "assistant"}:
            continue
        latest_ai_text = flatten_message_content(message).strip()
        break
    existing_governed_text = str(state.system.governed_output_text or "").strip()
    existing_preview_text = str(state.system.preview_text or state.system.final_text or state.system.final_answer or "").strip()
    if not existing_governed_text and existing_preview_text and latest_ai_text == existing_preview_text:
        existing_governed_text = existing_preview_text

    if existing_governed_text:
        patch: Dict[str, object] = {
            "reasoning": {
                "phase": phase,
                "last_node": "response_node",
            },
            "system": {
                "governed_output_text": existing_governed_text,
                "governed_output_status": str(state.system.governed_output_status or "finalized"),
                "governed_output_ready": True,
                "final_text": existing_governed_text,
                "final_answer": existing_governed_text,
            },
        }
        if latest_ai_text != existing_governed_text:
            patch["conversation"] = {
                "messages": [AIMessage(content=[{"type": "text", "text": existing_governed_text}])],
            }
        return stamp_patch_with_assertion_binding(state, patch)

    raw_intent = state.conversation.intent
    if isinstance(raw_intent, str):
        intent_goal = raw_intent
    else:
        intent_goal = getattr(raw_intent, "goal", "") or ""
    flags = state.reasoning.flags or {}
    intent_category = (
        str(
            getattr(raw_intent, "intent_category", "")
            if raw_intent is not None and not isinstance(raw_intent, str)
            else ""
        ).strip()
        or str(
            getattr(raw_intent, "routing_hint", "")
            if raw_intent is not None and not isinstance(raw_intent, str)
            else ""
        ).strip()
        or str(flags.get("frontdoor_intent_category") or flags.get("intent_category") or "").strip()
    )

    raw_calc_results = state.working_profile.calc_results
    calc_results = _as_dict(raw_calc_results)
    extracted_params = _as_dict(state.working_profile.extracted_params)
    engineering_profile = _as_dict(state.working_profile.engineering_profile)
    rag_context = str(state.reasoning.context or "")
    panel_material = _as_dict(wm.panel_material)
    panel_rag_context = str(panel_material.get("rag_context") or "")
    panel_rag_synthesized = str(panel_material.get("rag_synthesized") or "")
    rag_response_text = (
        wm.response_text
        or wm.knowledge_material
        or panel_rag_synthesized
    )

    design_notes = wm.design_notes or {}
    response_kind = wm.response_kind or phase
    requires_rag = bool(
        state.reasoning.requires_rag
        or state.reasoning.need_sources
        or flags.get("requires_rag")
        or flags.get("need_sources")
    )
    context = {
        "ask_missing_request": ask_missing,
        "intent_goal": intent_goal,
        "intent_category": intent_category,
        "requires_rag": requires_rag,
        "calc_results": calc_results,
        "extracted_params": extracted_params,
        "engineering_profile": engineering_profile,
        "design_notes": design_notes,
        "response_kind": response_kind,
        "response_text": wm.response_text,
        "rag_response_text": rag_response_text,
        "knowledge_material": wm.knowledge_material,
        "knowledge_lifetime": wm.knowledge_lifetime,
        "knowledge_generic": wm.knowledge_generic,
        "context": rag_context,
        "rag_context": rag_context,
        "panel_material": panel_material,
        "panel_rag_context": panel_rag_context,
        "panel_rag_synthesized": panel_rag_synthesized,
        "error": state.system.error,
        "phase": phase,
    }

    text = existing_preview_text or render_template("response_router.j2", context)
    if _should_use_light_llm_summary(
        state=state,
        intent_goal=intent_goal,
        response_kind=response_kind,
        calc_results=calc_results,
    ):
        summarized = _light_llm_summary(
            base_text=text,
            design_notes=design_notes if isinstance(design_notes, dict) else {},
            calc_results=calc_results,
        )
        if summarized:
            text = summarized

    if str(state.system.error or "").strip() == _PARTIAL_EXPERT_FAILURE_ERROR:
        if _PARTIAL_EXPERT_FAILURE_WARNING not in text:
            text = (
                f"{_PARTIAL_EXPERT_FAILURE_WARNING}\n\n{text}"
                if text.strip()
                else _PARTIAL_EXPERT_FAILURE_WARNING
            )

    patch = {
        "conversation": {
            "messages": [AIMessage(content=[{"type": "text", "text": text}])],
        },
        "reasoning": {
            "phase": state.reasoning.phase or "final",
            "last_node": "response_node",
        },
        "system": {
            "governed_output_text": text,
            "governed_output_status": "legacy_terminal",
            "governed_output_ready": True,
            "final_text": text,
            "final_answer": text,
        },
    }
    return stamp_patch_with_assertion_binding(state, patch)


__all__ = ["response_node"]
