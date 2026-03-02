"""Route node after frontdoor intent classification.

This node decides whether to:
- short-circuit into smalltalk
- run deterministic KB fast path
- jump directly into supervisor-driven expert flows
- continue with the full P1-P4 design pipeline
"""

from __future__ import annotations

import re
from typing import List

import structlog
from langgraph.types import Command

from app.langgraph_v2.state import SealAIState, WorkingProfile

logger = structlog.get_logger("langgraph_v2.route_after_frontdoor")
_TEMPERATURE_C_PATTERN = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*°?\s*c\b", re.IGNORECASE)
_SUITABILITY_TERMS = (
    "einsatzbarkeit",
    "einsetzbar",
    "geeignet",
    "tauglich",
)
_EXTREME_TEMP_LOW_C = -50.0
_EXTREME_TEMP_HIGH_C = 200.0


def _normalize_task_intents(raw: object) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if value:
            out.append(value)
    return out


def _latest_user_text(state: SealAIState) -> str:
    for msg in reversed(list(state.messages or [])):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            return str(getattr(msg, "content", "") or "")
    return ""


def _query_temperatures_c(state: SealAIState) -> List[float]:
    values: List[float] = []
    params = getattr(state, "parameters", None)
    if params is not None:
        for field in ("temperature_C", "temperature_min", "temperature_max"):
            raw = getattr(params, field, None)
            if raw is None:
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue

    user_text = _latest_user_text(state)
    for match in _TEMPERATURE_C_PATTERN.finditer(user_text):
        raw = match.group(1).replace(",", ".")
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


def _is_active_resume_session(state: SealAIState) -> bool:
    classification = str(getattr(state, "router_classification", "") or "").strip().lower()
    if classification == "resume":
        return True
    if bool(getattr(state, "awaiting_user_confirmation", False)):
        return True
    if bool((state.pending_action or "").strip()):
        return True
    if bool(getattr(state, "qgate_has_blockers", False)):
        return True
        
    # State Continuity: If we have an existing profile AND new parameters were extracted 
    # in this turn (indicated by router_classification == 'follow_up'), prioritize resuming.
    if state.working_profile and classification == "follow_up":
        return True
        
    return False


def _is_extreme_suitability_query(state: SealAIState) -> bool:
    user_text = _latest_user_text(state).strip().lower()
    if not user_text:
        return False
    if not any(term in user_text for term in _SUITABILITY_TERMS):
        return False
    return any((temp < _EXTREME_TEMP_LOW_C or temp > _EXTREME_TEMP_HIGH_C) for temp in _query_temperatures_c(state))


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

    if _is_active_resume_session(state):
        logger.info(
            "route_after_frontdoor.resume_design_pipeline_priority",
            category=category,
            goal=intent.goal,
            needs_pricing=bool(flags.get("needs_pricing")),
        )
        flags["use_reasoning_core_r3"] = True
        return Command(update={"flags": flags}, goto="node_p1_context")

    if _is_extreme_suitability_query(state):
        logger.info("route_after_frontdoor.extreme_temp_suitability_kb_fast_path", category=category, goal=intent.goal)
        return Command(goto="frontdoor_parallel_fanout_node")

    # 1) Smalltalk
    if social_opening and not task_intents:
        logger.info("route_after_frontdoor.smalltalk", category=category, goal=intent.goal)
        return Command(goto="smalltalk_node")

    # 2) Troubleshooting
    if intent.goal == "troubleshooting_leakage" or "troubleshooting_leakage" in task_intents:
        logger.info("route_after_frontdoor.troubleshooting", category=category, goal=intent.goal)
        return Command(goto="troubleshooting_wizard_node")

    # 3) Engineering Calculation pipeline (Priority)
    if category == "ENGINEERING_CALCULATION":
        logger.info("route_after_frontdoor.design_pipeline_priority", category=category, goal=intent.goal)
        flags["use_reasoning_core_r3"] = True
        
        # RWDR Fast Path: if shaft diameter (d1) and speed (n) are present, shortcut to calc
        params = state.parameters
        d1 = params.shaft_diameter or params.get("d1") or params.get("shaft_d1_mm")
        n = params.speed_rpm or params.get("n") or params.get("rpm")
        
        if d1 is not None and n is not None:
            logger.info("route_after_frontdoor.rwdr_fast_path_triggered", d1=d1, n=n)
            flags["force_instant_calc"] = True
            
            # Fast-path needs WorkingProfile for calc_chemical_resistance (P4b)
            wp = state.working_profile or WorkingProfile()
            if wp.d1 is None: wp.d1 = float(d1)
            if wp.n is None: wp.n = float(n)
            if wp.medium is None: wp.medium = params.medium
            if wp.material is None and wp.elastomer_material is None:
                # Default material for RWDR if none provided in prompt/params
                wp.material = params.elastomer_material or "NBR"

            return Command(update={"flags": flags, "working_profile": wp}, goto="node_p4b_calc_render")

        return Command(update={"flags": flags}, goto="node_p1_context")

    # 4) Deterministic KB fast path
    if (
        bool(getattr(state, "requires_rag", False))
        or bool(getattr(state, "need_sources", False))
        or category in {"MATERIAL_RESEARCH", "COMMERCIAL"}
        or "material_research" in task_intents
        or "commercial" in task_intents
    ):
        logger.info("route_after_frontdoor.kb_fast_path", category=category, goal=intent.goal)
        return Command(goto="frontdoor_parallel_fanout_node")

    # 5) Explanation/Comparison
    if intent.goal == "explanation_or_comparison" or "general_knowledge" in task_intents:
        logger.info("route_after_frontdoor.comparison", category=category, goal=intent.goal)
        return Command(goto="supervisor_policy_node")

    # 6) Full design pipeline fallback
    logger.info("route_after_frontdoor.design_pipeline", category=category, goal=intent.goal)
    flags["use_reasoning_core_r3"] = True
    return Command(update={"flags": flags}, goto="node_p1_context")


__all__ = ["route_after_frontdoor_node"]
