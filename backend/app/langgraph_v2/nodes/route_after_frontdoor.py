"""Route node after frontdoor intent classification.

This node decides whether to:
- short-circuit into smalltalk
- run deterministic KB fast path
- jump directly into supervisor-driven expert flows
- continue with the full P1-P4 design pipeline
"""

from __future__ import annotations

from typing import List

import structlog
from langgraph.types import Command

from app.langgraph_v2.state import SealAIState

logger = structlog.get_logger("langgraph_v2.route_after_frontdoor")


def _normalize_task_intents(raw: object) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if value:
            out.append(value)
    return out


def route_after_frontdoor_node(state: SealAIState) -> Command:
    """Route based on frontdoor_discovery_node outputs."""
    intent = state.intent
    flags = dict(state.flags or {})
    task_intents = _normalize_task_intents(flags.get("frontdoor_task_intents"))
    category = str(flags.get("frontdoor_intent_category") or "").strip().upper()
    social_opening = bool(flags.get("frontdoor_social_opening"))

    if intent is None:
        logger.warning("route_after_frontdoor.no_intent_fallback", fallback="node_p1_context")
        return Command(goto="node_p1_context")

    # 1) Smalltalk
    if social_opening and not task_intents:
        logger.info("route_after_frontdoor.smalltalk", category=category, goal=intent.goal)
        return Command(goto="smalltalk_node")

    # 2) Troubleshooting
    if intent.goal == "troubleshooting_leakage" or "troubleshooting_leakage" in task_intents:
        logger.info("route_after_frontdoor.troubleshooting", category=category, goal=intent.goal)
        return Command(goto="supervisor_policy_node")

    # 3) Deterministic KB fast path
    if (
        bool(getattr(state, "requires_rag", False))
        or bool(getattr(state, "need_sources", False))
        or category in {"MATERIAL_RESEARCH", "COMMERCIAL"}
        or "material_research" in task_intents
        or "commercial" in task_intents
    ):
        logger.info("route_after_frontdoor.kb_fast_path", category=category, goal=intent.goal)
        return Command(goto="frontdoor_parallel_fanout_node")

    # 4) Explanation/Comparison
    if intent.goal == "explanation_or_comparison" or "general_knowledge" in task_intents:
        logger.info("route_after_frontdoor.comparison", category=category, goal=intent.goal)
        return Command(goto="supervisor_policy_node")

    # 5) Full design pipeline
    logger.info("route_after_frontdoor.design_pipeline", category=category, goal=intent.goal)
    return Command(goto="node_p1_context")


__all__ = ["route_after_frontdoor_node"]
