"""Intent and routing nodes for LangGraph v2."""
from __future__ import annotations

import re
from typing import Dict
import structlog

from app.langgraph_v2.constants import MODEL_NANO
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.types import PhaseLiteral
from app.langgraph_v2.utils.llm_factory import run_llm
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj
from app.langgraph_v2.utils.messages import latest_user_text

logger = structlog.get_logger("langgraph_v2.nodes_intent")

def _ui_state_payload(state: SealAIState, step: str, label: str) -> Dict[str, object]:
    ui_state = dict(state.ui_state or {})
    ui_state.update({"current_step": step, "current_label": label})
    return {"ui_state": ui_state}


def entry_router_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Initial router: move into intent detection.
    """
    return {
        "phase": _safe_phase("intent"),
        "last_node": "entry_router_node",
    }

def intent_projector_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Semantic intent classifier using LLM.
    """
    text = latest_user_text(state.get("messages"))

    if not text.strip() or _looks_like_smalltalk(text):
        ui_payload = _ui_state_payload(
            state, "intent", "Ich ordne den Intent ein, smalltalk/klar."
        )
        return {
            "intent": {
                "goal": "smalltalk",
                "domain": "general",
                "complexity": "low",
                "needs_sources": False,
            },
            "phase": _safe_phase("intent"),
            "last_node": "intent_projector_node",
            **ui_payload,
        }

    prompt = (
        "Du bist ein Intent-Classifier für den SealAI-Dichtungsberater. "
        "Analysiere die Eingabe und entscheide:"
        "goal ∈ {design_recommendation, explanation_or_comparison, troubleshooting_leakage}, "
        "domain ∈ {sealing_technology, general}, "
        "complexity ∈ {low, medium, high}, "
        "needs_sources ∈ {true, false}. "
        "Antwortform: JSON."
    )

    try:
        response_text = run_llm(
            model=MODEL_NANO,
            prompt=text,
            system=prompt,
            temperature=0.0,
            metadata={
                "run_id": state.run_id,
                "thread_id": state.thread_id,
                "user_id": state.user_id,
                "node": "intent_projector_node",
            },
        )
        data, _ = extract_json_obj(response_text, default={})
        goal = data.get("goal") or "design_recommendation"
        domain = data.get("domain") or "sealing_technology"
        complexity = data.get("complexity") or "medium"
        needs_sources = bool(data.get("needs_sources"))
    except Exception as exc:
        logger.error(
            "intent_projector_node_failed",
            run_id=state.run_id,
            thread_id=state.thread_id,
            error=str(exc),
        )
        goal = "design_recommendation"
        domain = "sealing_technology"
        complexity = "medium"
        needs_sources = False

    intent = {
        "goal": goal,
        "domain": domain,
        "complexity": complexity,
        "needs_sources": needs_sources,
    }

    return {
        "intent": intent,
        "phase": _safe_phase("intent"),
        "last_node": "intent_projector_node",
        **_ui_state_payload(
            state,
            "intent",
            "Ich ordne Ihre Anfrage einem Beratungsmodus zu.",
        ),
    }


def _looks_like_smalltalk(text: str) -> bool:
    """
    Heuristic for short greetings/thanks that should bypass the LLM.
    """
    normalized = re.sub(r"[!?.]+$", "", text or "").strip().lower()
    normalized = normalized.translate(str.maketrans({"ß": "ss", "ü": "u", "ä": "a", "ö": "o"}))
    normalized = re.sub(r"\s+", " ", normalized)

    # keep the heuristic narrow to avoid swallowing technical requests
    SMALLTALK_PATTERNS = [
        r"^(hallo|hi|hey)$",
        r"^(servus|moin)$",
        r"^(gruss dich|grues dich|gruezi|gruss gott|grussgott)$",
        r"^(guten (morgen|tag|abend))$",
        r"^(danke|dankeschoen|danke dir|thx)$",
    ]
    return any(re.match(pat, normalized) for pat in SMALLTALK_PATTERNS)


def _safe_phase(candidate: PhaseLiteral | str) -> PhaseLiteral:
    """Return candidate if it is a valid PhaseLiteral, else default to 'intent'."""
    valid = getattr(PhaseLiteral, "__args__", ())
    text = str(candidate)
    if text in valid:
        return text  # type: ignore[return-value]
    return "intent"  # type: ignore[return-value]

__all__ = ["entry_router_node", "intent_projector_node"]
