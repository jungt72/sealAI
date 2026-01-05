from __future__ import annotations

import os
from typing import Any, Dict

from app.langgraph.prompts.prompt_loader import render_prompt
from app.langgraph.state import (
    SealAIState,
    format_requirements_summary,
    missing_requirement_fields,
)

MIN_COVERAGE = float(os.getenv("RWD_MIN_COVERAGE", "0.7"))


def rwd_confirm_node(state: SealAIState) -> Dict[str, Any]:
    coverage = float(state.get("requirements_coverage") or 0.0)
    requirements = state.get("rwd_requirements") or {}
    slots = dict(state.get("slots") or {})
    updates: Dict[str, Any] = {"slots": slots}

    if slots.get("task_mode_hint") == "simple_direct_output":
        updates["phase"] = "auswahl"
        slots.setdefault("rwd_confirmation", "simple_task_bypass")
        return updates

    if coverage >= MIN_COVERAGE:
        summary = format_requirements_summary(requirements)
        slots["rwd_confirmation"] = summary
        updates["phase"] = "berechnung"
        return updates

    missing = missing_requirement_fields(requirements)
    if not missing:
        missing = ["machine", "application", "medium"]
    labels = [field.replace("_", " ") for field in missing]
    text = render_prompt(
        "rwd_confirm_missing.de.j2",
        missing_fields=labels[:6],
        has_more=len(labels) > 6,
    )
    slots["candidate_answer"] = text
    slots["candidate_source"] = "rwd_confirm_missing"
    updates["phase"] = "bedarfsanalyse"
    return updates


__all__ = ["rwd_confirm_node"]
