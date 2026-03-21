from __future__ import annotations

from typing import Any, Dict, List
from app._legacy_v2.state.governance_types import CompletenessCategory, CompletenessDepth
from app._legacy_v2.state import SealAIState
from app._legacy_v2.utils.assertion_cycle import is_artifact_stale

def compute_risk_driven_completeness(state: SealAIState) -> Dict[str, Any]:
    """Blueprint v1.2 — Core Risk-Driven Completeness logic."""
    # Blueprint v1.2 — Staleness Constraint:
    # If ANY pillar indicates that derived artifacts are stale (due to a cycle increment),
    # the recommendation MUST NOT be considered ready until analysis nodes have re-run.
    artifacts_stale = is_artifact_stale(state)

    wp = state.working_profile
    ep = state.engineering_profile
    missing_technical: List[str] = []
    missing_qualification: List[str] = []

    # 1. Technical Unknowns (Highest Risk)
    # Check canonical fields in WorkingProfile (wp) and legacy fallbacks in engineering_profile (ep)
    for key in ("medium", "pressure_bar", "temperature_c"):
        legacy_key = "pressure_max_bar" if key == "pressure_bar" else "temperature_max_c" if key == "temperature_c" else key
        if not getattr(wp, key, None) and not getattr(ep, legacy_key, None) and not getattr(ep, key, None):
            missing_technical.append(key)

    # 2. Qualification Unknowns (Medium Risk)
    for key in ("shaft_diameter", "speed_rpm"):
        if not getattr(wp, key, None) and not getattr(ep, key, None):
            missing_qualification.append(key)

    # 3. Derive Depth Level
    depth = CompletenessDepth.PRECHECK.value
    if not missing_technical:
        depth = CompletenessDepth.PREQUALIFICATION.value
        if not missing_qualification:
            depth = CompletenessDepth.CRITICAL_REVIEW.value

    # 4. Coverage Score (weighted)
    # Technical core fields = 60%, Qualification fields = 40%
    tech_score = (3 - len(missing_technical)) / 3.0
    qual_score = (2 - len(missing_qualification)) / 2.0
    coverage_score = (tech_score * 0.6) + (qual_score * 0.4)

    # 5. Readiness (v1.2 threshold)
    # Threshold 0.8 requires all tech core + at least half of qualification.
    # HARD GATE: must NOT be stale.
    recommendation_ready = (
        not artifacts_stale 
        and depth != CompletenessDepth.PRECHECK.value 
        and coverage_score >= 0.8
    )

    return {
        "missing_technical": missing_technical,
        "missing_qualification": missing_qualification,
        "completeness_depth": depth,
        "coverage_score": coverage_score,
        "recommendation_ready": recommendation_ready,
        "artifacts_stale": artifacts_stale,
    }
