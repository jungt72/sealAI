"""Deterministic combinatorial chemistry/mechanics guard.

Runs before router/frontdoor so blocker conditions are captured before any
LLM-assisted reasoning path is entered.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List

import structlog
from langgraph.types import Command

from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.services.rag.state import ConflictRecord, WorkingProfile

logger = structlog.get_logger("langgraph_v2.combinatorial_chemistry_guard")


_FKM_BLOCKING_AMINE_PATTERN = re.compile(
    r"\b(monoethanolamin(?:e)?|mea|dea|morpholin(?:e)?|cyclohexylamin(?:e)?|aggressive?\s+amines?)\b",
    re.IGNORECASE,
)
_COMBINATORIAL_GUARD_RULESET_VERSION = "v1.0.0-20260227"
_COMBINATORIAL_GUARD_RULESET_SIGNATURE = (
    "CHEM_FKM_AMINE_BLOCKER|"
    "CHEM_FKM_AED_CERT_BLOCKER|"
    "CHEM_FKM_AED_CERT_UNKNOWN|"
    "MECH_HIGH_PRESSURE_GAP_BLOCKER"
)
_COMBINATORIAL_GUARD_VERSION_HASH = hashlib.sha256(
    f"{_COMBINATORIAL_GUARD_RULESET_VERSION}|{_COMBINATORIAL_GUARD_RULESET_SIGNATURE}".encode("utf-8")
).hexdigest()


def _norm_material(value: str | None) -> str:
    return str(value or "").strip().upper()


def _contains_blocking_amine(additives: str | None) -> bool:
    text = str(additives or "").strip()
    if not text:
        return False
    return bool(_FKM_BLOCKING_AMINE_PATTERN.search(text))

def _dedupe_conflicts(conflicts: List[ConflictRecord]) -> List[ConflictRecord]:
    deduped: List[ConflictRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for conflict in conflicts:
        key = (conflict.rule_id, conflict.severity, conflict.condition)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(conflict)
    return deduped


def evaluate_combinatorial_conflicts(profile: WorkingProfile) -> List[ConflictRecord]:
    """Evaluate deterministic blocker/warning rules over WorkingProfile."""
    conflicts: List[ConflictRecord] = []
    material = _norm_material(profile.material)
    medium = str(profile.medium or "").lower()
    additives = str(profile.medium_additives or "").lower()
    pressure = profile.pressure_max_bar
    temp_max = profile.temperature_max_c
    extrusion_gap = profile.extrusion_gap_mm
    dp_dt = profile.dp_dt_bar_per_s

    # 1. FKM + blocking amine chemistry (BLOCKER)
    # Generic mentions such as "amines" or "filming amines" are intentionally not blocked.
    if "FKM" in material and _contains_blocking_amine(additives):
        conflicts.append(
            ConflictRecord(
                rule_id="CHEM_FKM_AMINE_BLOCKER",
                severity="BLOCKER",
                title="FKM with amine additives",
                condition="material=FKM AND medium_additives contains amine",
                reason="Basenangriff auf FKM durch Amine — chemische Zerstörung.",
                recommendation="EPDM (aminbeständig) oder FFKM prüfen.",
            )
        )

    # 2. PU + hot water > 60°C (WARNING)
    if ("PU" in material or "POLYURETHAN" in material) and \
       any(w in medium for w in ["wasser", "water", "steam", "dampf"]) and \
       (temp_max is not None and temp_max > 60.0):
        conflicts.append(
            ConflictRecord(
                rule_id="CHEM_PU_HOT_WATER_WARNING",
                severity="WARNING",
                title="PU in hot water > 60°C",
                condition="material=PU AND medium=water AND temp > 60",
                reason="PU hydrolysiert bei Heißwasser über 60°C.",
                recommendation="EPDM oder FKM für Heißwasser-Anwendungen.",
            )
        )

    # 3. NBR + aromatics > 15% (BLOCKER)
    if "NBR" in material and \
       any(a in (medium + additives) for a in ["aromat", "benzol", "toluol", "xylol", "benzene", "toluene", "xylene", "kraftstoff", "fuel"]):
        conflicts.append(
            ConflictRecord(
                rule_id="CHEM_NBR_AROMATIC_BLOCKER",
                severity="BLOCKER",
                title="NBR with aromatics > 15%",
                condition="material=NBR AND medium/additives contains aromatics",
                reason="NBR quillt stark bei Aromatengehalt >15%.",
                recommendation="FKM für aromatische Kohlenwasserstoffe.",
            )
        )

    # 4. PTFE-Backups + high dp_dt (WARNING)
    if "PTFE" in material and dp_dt is not None and dp_dt > 10.0:
        conflicts.append(
            ConflictRecord(
                rule_id="MECH_PTFE_DPDT_WARNING",
                severity="WARNING",
                title="PTFE-Backups at high dp/dt",
                condition="material=PTFE AND dp_dt > 10.0",
                reason="PTFE-Backup-Ringe versagen bei hoher Druckaufbaurate (dp/dt > 10 bar/s).",
                recommendation="Extrusionsspalt-Berechnung erforderlich; verstärkte Backup-Ringe prüfen.",
            )
        )

    if "FKM" in material and bool(profile.aed_required):
        if profile.compound_aed_certified is False:
            conflicts.append(
                ConflictRecord(
                    rule_id="CHEM_FKM_AED_CERT_BLOCKER",
                    severity="BLOCKER",
                    title="AED required but compound not certified",
                    condition="material=FKM AND aed_required=true AND compound_aed_certified=false",
                    reason="Rapid gas decompression risk requires an AED-certified compound.",
                    recommendation="Use an AED-certified compound and provide certification evidence for the selected grade.",
                )
            )
        elif profile.compound_aed_certified is None:
            conflicts.append(
                ConflictRecord(
                    rule_id="CHEM_FKM_AED_CERT_UNKNOWN",
                    severity="WARNING",
                    title="AED certification evidence missing",
                    condition="material=FKM AND aed_required=true AND compound_aed_certified is null",
                    reason="AED relevance is flagged but certification status is unknown.",
                    recommendation="Collect compound-level AED certification before final recommendation.",
                )
            )

    if pressure is not None and extrusion_gap is not None and pressure > 100.0 and extrusion_gap > 0.3:
        conflicts.append(
            ConflictRecord(
                rule_id="MECH_HIGH_PRESSURE_GAP_BLOCKER",
                severity="BLOCKER",
                title="Extrusion risk at high pressure and large gap",
                condition="pressure_max_bar > 100 AND extrusion_gap_mm > 0.3",
                reason="Large extrusion gap at high pressure can lead to seal extrusion/failure.",
                recommendation="Reduce gap, add backup ring, or select higher extrusion-resistant configuration.",
            )
        )

    return conflicts


def combinatorial_chemistry_guard_node(state: SealAIState) -> Command:
    """LangGraph node enforcing deterministic combinatorial safety checks."""
    current_profile = state.working_profile.engineering_profile or WorkingProfile()
    new_conflicts = evaluate_combinatorial_conflicts(current_profile)
    existing_conflicts = list(getattr(current_profile, "conflicts_detected", []) or [])
    merged_conflicts = _dedupe_conflicts([*existing_conflicts, *new_conflicts])
    has_blocker = any(conflict.severity == "BLOCKER" for conflict in new_conflicts)

    next_profile = current_profile.model_copy(
        update={
            "conflicts_detected": merged_conflicts,
            "risk_mitigated": not has_blocker,
        }
    )

    flags: Dict[str, object] = dict(state.reasoning.flags or {})
    flags.update(
        {
            "combinatorial_chemistry_guard_ran": True,
            "combinatorial_chemistry_conflict_count": len(new_conflicts),
            "combinatorial_chemistry_has_blocker": has_blocker,
            "combinatorial_chemistry_blocker_rule_ids": [
                conflict.rule_id for conflict in new_conflicts if conflict.severity == "BLOCKER"
            ],
            "combinatorial_guard_ruleset_version": _COMBINATORIAL_GUARD_RULESET_VERSION,
            "combinatorial_guard_version_hash": _COMBINATORIAL_GUARD_VERSION_HASH,
        }
    )

    wm = state.reasoning.working_memory or WorkingMemory()
    diagnostic_data = dict(getattr(wm, "diagnostic_data", {}) or {})
    diagnostic_data.update(
        {
            "combinatorial_guard_ruleset_version": _COMBINATORIAL_GUARD_RULESET_VERSION,
            "combinatorial_guard_version_hash": _COMBINATORIAL_GUARD_VERSION_HASH,
        }
    )
    next_working_memory = wm.model_copy(
        update={
            "diagnostic_data": diagnostic_data,
        }
    )

    if new_conflicts:
        logger.warning(
            "combinatorial_chemistry_guard_conflicts_detected",
            thread_id=state.conversation.thread_id,
            run_id=state.system.run_id,
            has_blocker=has_blocker,
            conflict_count=len(new_conflicts),
            blocker_rules=[conflict.rule_id for conflict in new_conflicts if conflict.severity == "BLOCKER"],
        )

    if has_blocker:
        next_node = "request_clarification_node"
    else:
        next_node = "reasoning_core_node" if bool(flags.get("use_reasoning_core_r3")) else "node_router"

    return Command(
        update={
            "working_profile": {"engineering_profile": next_profile},
            "reasoning": {
                "last_node": "combinatorial_chemistry_guard_node",
                "working_memory": next_working_memory,
                "flags": flags,
            },
        },
        goto=next_node,
    )


__all__ = [
    "evaluate_combinatorial_conflicts",
    "combinatorial_chemistry_guard_node",
]
