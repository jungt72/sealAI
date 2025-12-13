# backend/app/langgraph_v2/nodes/nodes_supervisor.py
from __future__ import annotations

from typing import Any, Dict, List

from app.langgraph_v2.sealai_graph_v2 import log_state_debug
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.messages import latest_user_text

YES_KEYWORDS: List[str] = [
    "ja",
    "gerne",
    "bitte empfehle",
    "mach eine empfehlung",
    "go",
    "ok, mach weiter",
    "ja bitte",
    "leg los",
]
NO_KEYWORDS: List[str] = [
    "nein",
    "erst später",
    "nicht jetzt",
    "später",
    "noch nicht",
    "noch nicht bereit",
]

_REQUIRED_PARAMS_FOR_READY: List[str] = [
    "medium",
    "pressure_bar",
    "temperature_C",
    "shaft_diameter",
    "speed_rpm",
]

_READY_THRESHOLD = 0.8


def _compute_coverage(required: List[str], missing: List[str]) -> float:
    if not required:
        return 1.0
    score = (len(required) - len(missing)) / len(required)
    return max(0.0, min(1.0, score))


def _infer_missing_params(state: SealAIState, required: List[str]) -> List[str]:
    params = state.parameters
    missing: List[str] = []
    for key in required:
        value = getattr(params, key, None)
        if value is None or value == "":
            missing.append(key)
    return missing


def supervisor_logic_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("supervisor_logic_node", state)
    _maybe_set_recommendation_go(state)
    wm = state.working_memory or WorkingMemory()

    missing = _infer_missing_params(state, _REQUIRED_PARAMS_FOR_READY)
    coverage_score = _compute_coverage(_REQUIRED_PARAMS_FOR_READY, missing)
    recommendation_ready = coverage_score >= _READY_THRESHOLD
    return {
        "working_memory": wm,
        # WICHTIG: Phase auf einen gültigen PhaseLiteral-Wert setzen
        "phase": "intent",
        "last_node": "supervisor_logic_node",
        # Deterministic readiness/coverage for supervisor gating.
        "missing_params": missing,
        "coverage_gaps": missing,
        "coverage_score": coverage_score,
        "recommendation_ready": recommendation_ready,
    }


def supervisor_route(state: SealAIState) -> str:
    goal = getattr(state.intent, "goal", "smalltalk") if state.intent else "smalltalk"
    ready = bool(getattr(state, "recommendation_ready", False))
    go = bool(getattr(state, "recommendation_go", False))
    if goal == "design_recommendation":
        if not ready:
            return "intermediate"
        if go:
            return "design_flow"
        return "confirm"
    if goal == "explanation_or_comparison":
        return "comparison"
    if goal == "troubleshooting_leakage":
        return "troubleshooting"
    if goal == "out_of_scope":
        return "out_of_scope"
    return "smalltalk"


def _maybe_set_recommendation_go(state: SealAIState) -> None:
    if state.recommendation_go:
        return
    last_message = latest_user_text(state.messages or [])
    if not last_message:
        return
    normalized = last_message.lower()
    if any(keyword in normalized for keyword in YES_KEYWORDS):
        state.recommendation_go = True
        return
    if any(keyword in normalized for keyword in NO_KEYWORDS):
        state.recommendation_go = False


__all__ = ["supervisor_logic_node", "supervisor_route"]
