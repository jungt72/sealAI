"""node_compound_filter — pre-screen compound candidates via Decision Matrix.

Runs after node_factcard_lookup (non-deterministic path) and before
supervisor_policy_node.

Responsibilities:
- Extract operating conditions from state (temp, pressure, medium, application)
- Screen all PTFE compounds via CompoundDecisionMatrix
- Store ranked candidate list in compound_filter_results
- Always passes through to supervisor_policy_node (never generates final answer)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from app.langgraph_v2.state import SealAIState

log = logging.getLogger("app.langgraph_v2.nodes.compound_filter")


def node_compound_filter(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """CompoundDecisionMatrix screening node.

    Always routes to supervisor_policy_node; only enriches state with
    pre-screened compound candidates.
    """
    try:
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix
    except Exception as exc:
        log.warning("compound_filter.import_failed", extra={"error": str(exc)})
        return {
            "compound_filter_results": {"error": str(exc), "candidates": []},
            "last_node": "node_compound_filter",
        }

    # ------------------------------------------------------------------
    # Build conditions from state parameters
    # ------------------------------------------------------------------
    parameters = state.parameters
    conditions: Dict[str, Any] = {}
    query_text = ""
    for msg in reversed(state.messages or []):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            query_text = str(getattr(msg, "content", "") or "")
            break
    query_lower = query_text.lower()

    if parameters:
        temp_max = getattr(parameters, "temperature_max", None)
        temp_min = getattr(parameters, "temperature_min", None)
        pressure = getattr(parameters, "pressure_bar", None)
        medium = getattr(parameters, "medium", None)

        if temp_max is not None:
            conditions["temp_max_c"] = float(temp_max)
        if temp_min is not None:
            conditions["temp_min_c"] = float(temp_min)
        if pressure is not None:
            conditions["pressure_max_bar"] = float(pressure)
        if medium:
            # Normalize medium to medium_id for hard exclusion check
            medium_id = medium.lower().replace(" ", "_").replace("-", "_")
            conditions["medium_id"] = medium_id
            tags = []
            if any(x in medium_id for x in ("hf", "hydrofluoric")):
                tags.append("HF")
            if any(x in medium_id for x in ("alkali", "naoh", "koh")):
                tags.append("strong_alkali")
            if any(x in medium_id for x in ("oxidizer", "chlorine", "oxygen", "f2")):
                tags.append("oxidizer")
            if tags:
                conditions["media_tags"] = tags

        shaft_hardness = getattr(parameters, "shaft_hardness", None)
        if shaft_hardness:
            match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(shaft_hardness))
            if match:
                conditions["counterface_hardness_hrc"] = float(match.group(0).replace(",", "."))
        shaft_material = getattr(parameters, "shaft_material", None)
        if shaft_material:
            conditions["counterface_material"] = str(shaft_material).lower()

    if "aluminum" in query_lower or "aluminium" in query_lower or "soft aluminum" in query_lower:
        conditions["counterface_material"] = "aluminum_soft"
    if "brass" in query_lower or "messing" in query_lower:
        conditions["counterface_material"] = "brass"
    if "bronze" in query_lower:
        conditions["counterface_material"] = "bronze"
    if "soft shaft" in query_lower or "weiche welle" in query_lower:
        conditions.setdefault("counterface_hardness_hrc", 30.0)

    # Application type from intent or flags
    intent = state.intent
    if intent:
        knowledge_type = getattr(intent, "knowledge_type", None)
        if knowledge_type:
            conditions["application_type"] = str(knowledge_type).lower()

    # ------------------------------------------------------------------
    # Run screening
    # ------------------------------------------------------------------
    matrix = CompoundDecisionMatrix.get_instance()
    candidates = matrix.screen(conditions)

    log.info(
        "compound_filter.done",
        extra={
            "total_candidates": len(candidates),
            "conditions_used": list(conditions.keys()),
            "run_id": state.run_id,
        },
    )

    compound_filter_results: Dict[str, Any] = {
        "candidates": [
            {
                "filler_id": e.get("filler_id"),
                "compound_name": e.get("compound_name"),
                "score": e.get("score"),
                "food_grade": e.get("food_grade"),
                "rationale": e.get("rationale"),
                "recommended_for": e.get("recommended_for") or [],
            }
            for e in candidates
        ],
        "conditions_applied": conditions,
        "matrix_loaded": matrix.is_loaded,
    }

    return {
        "compound_filter_results": compound_filter_results,
        "last_node": "node_compound_filter",
    }


__all__ = ["node_compound_filter"]
