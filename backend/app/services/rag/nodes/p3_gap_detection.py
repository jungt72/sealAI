"""P3 Gap-Detection Node for SEALAI v4.4.0 (Sprint 5).

Runs in parallel with P2 (RAG Material-Lookup) after P1 (Context Extraction).

Responsibilities:
- Analyze the WorkingProfile to identify missing critical and optional parameters
- Compute coverage metrics
- Determine if the profile is recommendation-ready

Pure computation — no LLM call, no RAG call.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.services.rag.state import WorkingProfile

logger = structlog.get_logger("rag.nodes.p3_gap_detection")

# Minimum fields required for a seal recommendation
CRITICAL_FIELDS: frozenset[str] = frozenset({
    "medium",
    "pressure_max_bar",
    "temperature_max_c",
    "flange_standard",
    "flange_dn",
})

# All profile fields (mirror of WorkingProfile._PROFILE_FIELDS)
_ALL_PROFILE_FIELDS: frozenset[str] = frozenset({
    "medium",
    "medium_detail",
    "pressure_max_bar",
    "pressure_min_bar",
    "temperature_max_c",
    "temperature_min_c",
    "flange_standard",
    "flange_dn",
    "flange_pn",
    "flange_class",
    "bolt_count",
    "bolt_size",
    "cyclic_load",
    "emission_class",
    "industry_sector",
})

_OPTIONAL_FIELDS: frozenset[str] = _ALL_PROFILE_FIELDS - CRITICAL_FIELDS


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


def _compute_gap_report(profile: Optional[WorkingProfile]) -> Dict[str, Any]:
    """Compute gap report from a WorkingProfile."""
    if profile is None:
        return {
            "missing_critical": sorted(CRITICAL_FIELDS),
            "missing_optional": sorted(_OPTIONAL_FIELDS),
            "coverage_ratio": 0.0,
            "recommendation_ready": False,
            "high_impact_gaps": sorted(CRITICAL_FIELDS),
        }

    missing_critical: List[str] = []
    for field in sorted(CRITICAL_FIELDS):
        value = getattr(profile, field, None)
        if value is None:
            missing_critical.append(field)

    missing_optional: List[str] = []
    for field in sorted(_OPTIONAL_FIELDS):
        value = getattr(profile, field, None)
        if value is None and value is not False:
            # cyclic_load defaults to False, which is a valid value
            if field == "cyclic_load":
                continue
            missing_optional.append(field)

    coverage_ratio = profile.coverage_ratio()
    recommendation_ready = len(missing_critical) == 0

    return {
        "missing_critical": missing_critical,
        "missing_optional": missing_optional,
        "coverage_ratio": round(coverage_ratio, 4),
        "recommendation_ready": recommendation_ready,
        "high_impact_gaps": missing_critical,
    }


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p3_gap_detection(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P3 Gap-Detection — analyze WorkingProfile completeness.

    Wired as a parallel worker after node_p1_context (via Send).
    Feeds into node_p3_5_merge.
    """
    profile: Optional[WorkingProfile] = getattr(state, "working_profile", None)

    gap_report = _compute_gap_report(profile)

    logger.info(
        "p3_gap_detection_done",
        coverage_ratio=gap_report["coverage_ratio"],
        missing_critical_count=len(gap_report["missing_critical"]),
        recommendation_ready=gap_report["recommendation_ready"],
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    return {
        "gap_report": gap_report,
        "phase": PHASE.FRONTDOOR,
        "last_node": "node_p3_gap_detection",
    }


__all__ = ["node_p3_gap_detection", "CRITICAL_FIELDS", "_compute_gap_report"]
