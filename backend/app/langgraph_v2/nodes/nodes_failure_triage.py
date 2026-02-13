"""Deterministic failure-first triage gate."""

from __future__ import annotations

import re
from typing import Any, Dict

from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.messages import latest_user_text

_FAILURE_RE = re.compile(
    r"\b("
    r"leak|leaking|leckt|leckage|undicht|"
    r"failed|failure|seal failed|defekt|kaputt|ausfall|sudden failure|"
    r"extrusion|nibbling|blister|blistering|crack|cracking|wear|verschlei[sß]|"
    r"spiral twist|flat set|damage|schaden|gerissen|gebrochen"
    r")\b",
    re.IGNORECASE,
)
_DETAIL_RE = re.compile(
    r"\b(cuts?|schnitt|blister|blasen|flat set|druckverformung|nibbling|extrusion|"
    r"spiral twist|verdreht|wear|verschlei[sß]|crack|riss|cycles?|zyklen|depressurization|blowdown)\b",
    re.IGNORECASE,
)
_PHOTO_RE = re.compile(r"\b(photo|foto|bild|image|upload|anhang|attached)\b", re.IGNORECASE)


def _has_failure_signal(text: str) -> bool:
    return bool(_FAILURE_RE.search(text or ""))


def _intent_goal(state: SealAIState) -> str:
    intent = getattr(state, "intent", None)
    if isinstance(intent, dict):
        return str(intent.get("goal") or "").strip().lower()
    return str(getattr(intent, "goal", "") or "").strip().lower()


def _default_track(state: SealAIState) -> str:
    goal = _intent_goal(state)
    if goal in {"explanation_or_comparison", "generic_qa", "knowledge_only"}:
        return "knowledge"
    if goal == "troubleshooting_leakage":
        return "diagnostic"
    return "design"


def _has_evidence(text: str, failure_evidence: Dict[str, Any]) -> bool:
    if _PHOTO_RE.search(text or ""):
        return True
    if _DETAIL_RE.search(text or ""):
        return True
    photo_ids = list((failure_evidence or {}).get("photo_ids") or [])
    if photo_ids:
        return True
    tags = list((failure_evidence or {}).get("description_tags") or [])
    return bool(tags)


def failure_triage_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    text = latest_user_text(list(state.messages or [])) or ""
    existing_evidence = dict(getattr(state, "failure_evidence", {}) or {})
    failure_signal = _has_failure_signal(text)
    evidence_ready = _has_evidence(text, existing_evidence)
    risk_heatmap = dict(getattr(state, "risk_heatmap", {}) or {})

    if failure_signal and not evidence_ready:
        risk_heatmap["failure_evidence"] = "critical"
        questions = [
            "Upload photo of failed seal + damage area.",
            "Describe damage: cuts / blisters / flat set / nibbling / spiral twist.",
            "How long until failure + cycles + depressurization events?",
        ][:2]
        request = AskMissingRequest(
            missing_fields=["failure_photo_or_damage_evidence"],
            question=(
                "Kurzdiagnose zuerst: Bitte liefere Ausfallnachweise, bevor ich eine belastbare Empfehlung freigebe."
            ),
            reason="failure_evidence_required",
            questions=questions,
        )
        return {
            "failure_mode_active": True,
            "failure_evidence_missing": True,
            "failure_evidence": existing_evidence,
            "guardrail_escalation_reason": "failure_evidence_required",
            "ask_missing_request": request,
            "ask_missing_scope": "technical",
            "awaiting_user_input": True,
            "risk_heatmap": risk_heatmap,
            "rfq_ready": False,
            "conversation_track": "diagnostic",
            "phase": PHASE.VALIDATION,
            "last_node": "failure_triage_node",
        }

    if failure_signal and evidence_ready:
        risk_heatmap.setdefault("failure_evidence", "high")
        evidence = dict(existing_evidence)
        if _PHOTO_RE.search(text):
            evidence.setdefault("photo_hint", True)
        if _DETAIL_RE.search(text):
            evidence.setdefault("damage_description_present", True)
        return {
            "failure_mode_active": True,
            "failure_evidence_missing": False,
            "failure_evidence": evidence,
            "risk_heatmap": risk_heatmap,
            "conversation_track": "diagnostic",
            "phase": PHASE.VALIDATION,
            "last_node": "failure_triage_node",
        }

    return {
        "failure_mode_active": bool(getattr(state, "failure_mode_active", False)),
        "failure_evidence_missing": bool(getattr(state, "failure_evidence_missing", False)),
        "failure_evidence": existing_evidence,
        "risk_heatmap": risk_heatmap,
        "conversation_track": str(getattr(state, "conversation_track", "") or _default_track(state)),
        "phase": PHASE.VALIDATION,
        "last_node": "failure_triage_node",
    }


def failure_triage_router(state: SealAIState) -> str:
    if getattr(state, "failure_mode_active", False) and getattr(state, "failure_evidence_missing", False):
        return "ask_missing"
    if getattr(state, "awaiting_user_input", False) or getattr(state, "ask_missing_request", None):
        return "ask_missing"
    return "guardrail"


async def failure_triage_router_async(state: SealAIState) -> str:
    return failure_triage_router(state)


__all__ = ["failure_triage_node", "failure_triage_router", "failure_triage_router_async"]
