"""Safety gate evaluating synthesis results and routing risk."""
from __future__ import annotations

from typing import Any, Dict, List

from app.langgraph.io.validation import ensure_agent_output, ensure_safety
from .base import IOValidatedNode


def _collect_evidence(payload: Dict[str, Any]) -> int:
    evidences: List[Any] = []
    if "evidenz" in payload:
        raw = payload.get("evidenz")
        if isinstance(raw, list):
            evidences.extend(raw)
    if "agent_outputs" in payload:
        for item in payload.get("agent_outputs", []):
            try:
                model = ensure_agent_output(item)
            except Exception:
                continue
            data = getattr(model, "model_dump", None)
            if callable(data):
                evidences.extend(data().get("evidenz", []) or [])
            else:
                evidences.extend(model.dict().get("evidenz", []) or [])  # type: ignore[attr-defined]
    return len([e for e in evidences if e])


def _resolve_risk(payload: Dict[str, Any]) -> str:
    for key in ("risk", "routing_risk"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    classification = payload.get("classification") or {}
    if isinstance(classification, dict):
        risk = classification.get("risk")
        if isinstance(risk, str) and risk:
            return risk.lower()
    return "low"


def _has_normen_agent(payload: Dict[str, Any]) -> bool:
    for key in ("agents", "empfohlene_agenten", "involved_agents"):
        agents = payload.get(key)
        if isinstance(agents, (list, tuple, set)):
            for agent in agents:
                if isinstance(agent, str) and agent.lower() == "normen":
                    return True
    agent = payload.get("agent")
    if isinstance(agent, str) and agent.lower() == "normen":
        return True
    classification = payload.get("classification") or {}
    if isinstance(classification, dict):
        agents = classification.get("empfohlene_agenten")
        if isinstance(agents, list):
            return any(isinstance(a, str) and a.lower() == "normen" for a in agents)
    return False


def _override_result(payload: Dict[str, Any], default: str) -> str:
    override = payload.get("safety_override") or payload.get("force_result")
    if isinstance(override, str) and override.lower() in {"pass", "block_with_reason"}:
        return override.lower()
    return default


def _override_reason(payload: Dict[str, Any], default: str | None) -> str | None:
    reason = payload.get("safety_reason") or payload.get("reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return default


class SafetyGateNode(IOValidatedNode):
    """Decides final pass/block verdict based on risk, agents, and evidence."""

    _out_validator = ensure_safety

    def _run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        risk_value = _resolve_risk(payload)
        normen_active = _has_normen_agent(payload)
        evidence_count = _collect_evidence(payload)

        should_block = (risk_value != "low" or normen_active) and evidence_count == 0

        default_reason = None
        if should_block:
            default_reason = "fehlende Evidenz für kritische Empfehlung"
            if normen_active and risk_value != "low":
                default_reason = "Normen- oder Risiko-Check ohne Evidenz"
            elif normen_active:
                default_reason = "Normenprüfung ohne Evidenz"
            elif risk_value != "low":
                default_reason = "Erhöhtes Risiko ohne Evidenz"

        result = _override_result(payload, "block_with_reason" if should_block else "pass")
        reason = _override_reason(payload, default_reason)

        return {
            "schema_version": payload.get("schema_version") or "1.0.0",
            "result": result,
            "reason": reason,
        }


__all__ = ["SafetyGateNode"]
