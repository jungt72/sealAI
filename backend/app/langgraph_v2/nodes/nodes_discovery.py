from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from langchain.schema import HumanMessage, SystemMessage

from app.core.config import settings
from app.langgraph_v2.constants import PHASE, PhaseLiteral
from app.langgraph_v2.contracts import AskMissingRequest, Intent, IntentGoal
from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node  # Import core logic
from app.langgraph_v2.state import (
    SealAIState,
    TechnicalParameters,
    WorkingMemory,
)
from app.langgraph_v2.tools.parameter_tools import set_parameters
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.output_sanitizer import extract_json_obj
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_lww
from app.langgraph_v2.utils.state_debug import log_state_debug

logger = logging.getLogger(__name__)


def _ui_state_payload(state: SealAIState, step: str, label: str) -> Dict[str, Any]:
    return {
        "ui_state": {
            "current_step": step,
            "current_label": label,
        }
    }


def discovery_intake_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Alias: aktueller Entry-Point für Discovery."""
    return frontdoor_discovery_node(state, *_args, **_kwargs)

def discovery_summarize_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Fasst die Discovery-Informationen zusammen und schätzt Coverage/Missing ein."""
    wk = state.working_memory or WorkingMemory()

    # Wenn summary_raw aus der Frontdoor-Discovery existiert, nutze sie,
    # sonst direkt den letzten User-Text.
    summary_source = getattr(wk, "summary_raw", None) or latest_user_text(
        state.get("messages")
    )

    model = get_model_tier("nano")
    system = render_template("discovery_summarize.j2", {})
    reply_text = run_llm(
        model=model,
        prompt=summary_source or "",
        system=system,
        temperature=0.35,
        max_tokens=260,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "discovery_summarize_node",
        },
    )
    data, ok = extract_json_obj(reply_text, default={})
    summary = str(data.get("summary") or "").strip()
    try:
        coverage = float(data.get("coverage") or 0.0)
    except (TypeError, ValueError):
        coverage = 0.0
    raw_missing = data.get("missing") or []
    missing: List[str] = []
    if isinstance(raw_missing, list):
        missing = [str(item).strip() for item in raw_missing if str(item).strip()]
    elif raw_missing:
        missing = [str(raw_missing).strip()]

    wk_update = {
        "summary_clean": summary or summary_source or "",
        "coverage_notes": coverage,
    }
    try:
        wk = wk.model_copy(update=wk_update)
    except Exception:
        pass

    logger.info(
        "discovery_summarize_node_exit",
        run_id=state.run_id,
        thread_id=state.thread_id,
        coverage=coverage,
        missing=missing,
    )

    return {
        "discovery_summary": summary or None,
        "discovery_coverage": max(0.0, min(1.0, coverage)),
        "discovery_missing": missing[:3] or [],
        "working_memory": wk,
        "phase": PHASE.ENTRY,
        "last_node": "discovery_summarize_node",
        **_ui_state_payload(
            state,
            "discovery",
            "Ich prüfe, ob alle relevanten Informationen vorliegen.",
        ),
    }


def confirm_gate_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Entscheidet, ob noch Infos fehlen und baut ggf. eine Ask-Missing-Anfrage."""
    model = get_model_tier("nano")
    summary = (state.get("discovery_summary") or "").strip()
    coverage = state.get("discovery_coverage") or 0.0
    missing = state.get("discovery_missing") or []

    try:
        coverage = float(coverage)
    except (TypeError, ValueError):
        coverage = 0.0
    coverage = max(0.0, min(1.0, coverage))
    missing_text = "; ".join(str(item) for item in missing) if missing else "-"

    context = {
        "summary": summary,
        "coverage": coverage,
        "missing_text": missing_text,
    }
    
    full_text = render_template("confirm_gate.j2", context)
    parts = full_text.split("---", 1)
    if len(parts) == 2:
        system = parts[0].strip()
        prompt = parts[1].strip()
    else:
        system = "Du bist ein technischer Berater für Dichtungstechnik."
        prompt = full_text.strip()

    reply_text = run_llm(
        model=model,
        prompt=prompt,
        system=system,
        temperature=0.45,
        max_tokens=280,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "confirm_gate_node",
        },
    )

    ask_missing_request: AskMissingRequest | None = None
    ask_missing_scope = None

    # Nur wenn Coverage < 0.85 wirklich eine Ask-Missing-Runde starten
    if coverage < 0.85:
        question = (
            "Ich benötige noch ein paar Details zu Ihrem Anwendungsfall, um präzise weiterarbeiten zu können. "
            f"Fehlende Werte: {missing_text}."
        )
        ask_missing_request = AskMissingRequest(
            missing_fields=missing,
            question=question,
        )
        ask_missing_scope = "discovery"

    wm = state.working_memory or WorkingMemory()
    try:
        wm = wm.model_copy(
            update={
                "response_text": reply_text,
                "response_kind": "confirm_gate",
                "coverage_summary": summary,
            }
        )
    except Exception:
        pass

    intent = dict(state.intent or {})
    if not intent.get("goal"):
        intent["goal"] = "design_recommendation"

    return {
        "ask_missing_request": ask_missing_request,
        "ask_missing_scope": ask_missing_scope,
        "awaiting_user_input": bool(ask_missing_request),
        "phase": PHASE.INTENT,
        "last_node": "confirm_gate_node",
        "working_memory": wm,
        "intent": intent,
        **_ui_state_payload(
            state,
            "discovery",
            "Einige Details fehlen noch." if missing else "Alles klar, ich ordne den Intent ein.",
        ),
    }


__all__ = [
    "discovery_intake_node",
    "frontdoor_discovery_node",
    "discovery_summarize_node",
    "confirm_gate_node",
]
