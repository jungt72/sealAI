"""Deterministic policy firewall nodes for LangGraph v2."""

from __future__ import annotations

from typing import Dict, Any

import structlog

from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.policy_firewall import evaluate_policy

logger = structlog.get_logger("langgraph_v2.nodes_policy")


def _apply_policy_report(state: SealAIState, report: Dict[str, Any]) -> Dict[str, Any]:
    wm = state.working_memory or WorkingMemory()
    try:
        wm = wm.model_copy(update={"policy_notes": report})
    except Exception:
        pass
    return {
        "policy_report": report,
        "policy_status": report.get("status"),
        "working_memory": wm,
    }


def policy_preflight_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, Any]:
    """
    Pre-resume policy check (non-blocking).
    """
    report = evaluate_policy(state)
    logger.info(
        "policy_preflight_node",
        run_id=state.run_id,
        thread_id=state.thread_id,
        status=report.get("status"),
    )
    patch = _apply_policy_report(state, report)
    patch.update(
        {
            "phase": PHASE.VALIDATION,
            "last_node": "policy_preflight_node",
        }
    )
    return patch


def policy_firewall_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, Any]:
    """
    Mandatory ISO/DIN policy gate before final answer.
    If violations exist, trigger ask-missing for standards/parameters.
    """
    report = evaluate_policy(state)
    logger.info(
        "policy_firewall_node",
        run_id=state.run_id,
        thread_id=state.thread_id,
        status=report.get("status"),
        violations=len(report.get("violations") or []),
    )
    patch = _apply_policy_report(state, report)

    status = report.get("status")
    violations = list(report.get("violations") or [])
    if violations or status == "skipped":
        missing_fields = []
        for item in violations:
            if item.get("reason") == "missing_standard_reference":
                missing_fields.append("standard_reference")
            if item.get("reason") == "missing_parameters":
                missing_fields.extend(item.get("details", {}).get("missing", []))
            if item.get("reason") == "missing_application_context":
                missing_fields.append("application_type")
            if item.get("reason") == "missing_material_or_profile":
                missing_fields.extend(item.get("details", {}).get("missing", []))
        if status == "skipped" and not missing_fields:
            missing_fields.extend(["material", "profile"])
        missing_fields = [field for field in dict.fromkeys(missing_fields) if field]
        question = (
            "Vor der finalen Empfehlung fehlen noch ISO/DIN-relevante Angaben: "
            f"{', '.join(missing_fields)}. Bitte ergänze diese Punkte."
        )
        patch.update(
            {
                "ask_missing_request": AskMissingRequest(missing_fields=missing_fields, question=question),
                "ask_missing_scope": "technical",
                "awaiting_user_input": True,
            }
        )

    patch.update(
        {
            "phase": PHASE.VALIDATION,
            "last_node": "policy_firewall_node",
        }
    )
    return patch


__all__ = ["policy_preflight_node", "policy_firewall_node"]
