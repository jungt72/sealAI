"""Deterministic HITL severity triage node."""

from __future__ import annotations

import re
from typing import Any, Dict

import structlog
from langgraph.types import Command

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState

logger = structlog.get_logger("langgraph_v2.hitl_triage")

_SEV1_PATTERN = re.compile(
    r"\b(h2|wasserstoff|hydrogen|o2|sauerstoff|oxygen|hf|flusss?(?:a|ae)ure|hydrofluoric|atex\s*(zone)?\s*0|zone\s*0)\b",
    re.IGNORECASE,
)
_SEV2_STEAM_PATTERN = re.compile(r"\b(dampf|steam)\b", re.IGNORECASE)
_SEV2_AMINE_PATTERN = re.compile(
    r"\b(amine|amines|filming\s+amines?|monoethanolamin(?:e)?|mea|dea|morpholin(?:e)?)\b",
    re.IGNORECASE,
)
_SEV3_ATEX_PATTERN = re.compile(r"\b(atex\s*(zone)?\s*[12]|zone\s*[12])\b", re.IGNORECASE)

_SLA_BY_SEVERITY = {
    "SEV-1": "4h",
    "SEV-2": "12h",
    "SEV-3": "24h",
    "SEV-4": "48h",
}
_QUEUE_BY_SEVERITY = {
    "SEV-1": "hitl_queue_critical",
    "SEV-2": "hitl_queue_high",
    "SEV-3": "hitl_queue_medium",
    "SEV-4": "hitl_queue_low",
}


def _compose_profile_text(state: SealAIState) -> str:
    profile = state.working_profile
    if profile is None:
        return ""
    chunks = [
        str(getattr(profile, "medium", "") or ""),
        str(getattr(profile, "medium_detail", "") or ""),
        str(getattr(profile, "medium_additives", "") or ""),
        str(getattr(profile, "industry_sector", "") or ""),
    ]
    return " ".join(chunks).strip()


def _classify_severity(state: SealAIState) -> str:
    explicit = str(getattr(state, "safety_class", "") or "").strip().upper()
    if explicit in {"SEV-1", "SEV-2", "SEV-3", "SEV-4"}:
        return explicit

    profile = state.working_profile
    text_blob = _compose_profile_text(state)

    pressure = float(getattr(profile, "pressure_max_bar", 0.0) or 0.0) if profile is not None else 0.0
    temp = float(getattr(profile, "temperature_max_c", 0.0) or 0.0) if profile is not None else 0.0
    aed_required = bool(getattr(profile, "aed_required", False)) if profile is not None else False
    has_blocker = False
    if profile is not None:
        has_blocker = any(str(getattr(conflict, "severity", "") or "").upper() == "BLOCKER" for conflict in (profile.conflicts_detected or []))

    if _SEV1_PATTERN.search(text_blob):
        return "SEV-1"
    if pressure > 100.0:
        return "SEV-2"
    if _SEV2_STEAM_PATTERN.search(text_blob) and temp > 180.0:
        return "SEV-2"
    if _SEV2_AMINE_PATTERN.search(text_blob):
        return "SEV-2"
    if aed_required:
        return "SEV-2"
    if _SEV3_ATEX_PATTERN.search(text_blob):
        return "SEV-3"
    if temp > 200.0:
        return "SEV-3"
    if has_blocker:
        return "SEV-3"
    return "SEV-4"


def hitl_triage_node(state: SealAIState) -> Command:
    severity = _classify_severity(state)
    queue_name = _QUEUE_BY_SEVERITY[severity]
    sla = _SLA_BY_SEVERITY[severity]
    requires_hitl_pause = severity in {"SEV-1", "SEV-2"}

    flags = dict(state.flags or {})
    flags.update(
        {
            "hitl_triage_ran": True,
            "hitl_severity": severity,
            "hitl_queue": queue_name,
            "hitl_sla": sla,
            "hitl_pause_required": requires_hitl_pause,
        }
    )

    update: Dict[str, Any] = {
        "last_node": "hitl_triage_node",
        "safety_class": severity,
        "flags": flags,
    }

    if requires_hitl_pause:
        update.update(
            {
                "phase": PHASE.CONFIRM,
                "requires_human_review": True,
                "awaiting_user_confirmation": True,
                "pending_action": "hitl_signature_required",
                "confirm_status": "pending",
                "error": f"HITL review required ({severity}, SLA {sla}). Waiting for reviewer signature.",
            }
        )
        logger.warning(
            "hitl_triage_escalated",
            severity=severity,
            queue=queue_name,
            sla=sla,
            thread_id=state.thread_id,
            run_id=state.run_id,
        )
        return Command(update=update, goto="human_review_node")

    logger.info(
        "hitl_triage_passed_without_pause",
        severity=severity,
        queue=queue_name,
        sla=sla,
        thread_id=state.thread_id,
        run_id=state.run_id,
    )
    return Command(update=update, goto="worm_evidence_node")


__all__ = ["hitl_triage_node"]
