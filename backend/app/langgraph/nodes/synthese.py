"""Synthesis node assembling agent outputs into a unified recommendation."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.langgraph.io.schema import AgentOutput
from app.langgraph.io.validation import ensure_agent_output, ensure_synthesis
from .base import IOValidatedNode


def _safe_model_dump(model: Any) -> Dict[str, Any]:
    if model is None:
        return {}
    exporter = getattr(model, "model_dump", None)
    if callable(exporter):
        return exporter()
    to_dict = getattr(model, "dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(model, dict):
        return dict(model)
    return {}


def _issue_priority(text: str) -> int:
    lowered = text.lower()
    if "norm" in lowered or "iso" in lowered or "din" in lowered:
        return 0
    if "grenz" in lowered or "limit" in lowered or "temperatur" in lowered or "druck" in lowered:
        return 1
    if "kosten" in lowered or "preis" in lowered:
        return 2
    return 3


class SyntheseNode(IOValidatedNode):
    """Aggregates multiple agent outputs into a single synthesis result."""

    _out_validator = ensure_synthesis

    def _run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        outputs_raw = payload.get("agent_outputs") or payload.get("outputs") or []
        agent_outputs: List[AgentOutput] = []
        for item in outputs_raw:
            try:
                agent_outputs.append(ensure_agent_output(item))
            except Exception:
                continue

        if not agent_outputs and payload.get("synthesis"):
            existing = payload["synthesis"]
            if isinstance(existing, dict):
                return ensure_synthesis(existing).model_dump()

        recommendation = payload.get("empfehlung") or ""
        if not recommendation:
            for model in agent_outputs:
                data = _safe_model_dump(model)
                text = data.get("empfehlung") or data.get("begruendung")
                if isinstance(text, str) and text.strip():
                    recommendation = text.strip()
                    break
        if not recommendation:
            recommendation = "Keine Empfehlung verfügbar"

        alternativen: List[str] = []
        for model in agent_outputs[1:]:
            data = _safe_model_dump(model)
            text = data.get("empfehlung")
            if isinstance(text, str) and text.strip():
                alternativen.append(text.strip())

        uncertainties: List[Tuple[int, str]] = []
        for model in agent_outputs:
            data = _safe_model_dump(model)
            for entry in data.get("unsicherheiten", []) or []:
                if isinstance(entry, str) and entry.strip():
                    uncertainties.append((_issue_priority(entry), entry.strip()))
        if payload.get("unsicherheiten"):
            for entry in payload.get("unsicherheiten", []):
                if isinstance(entry, str) and entry.strip():
                    uncertainties.append((_issue_priority(entry), entry.strip()))
        uncertainties.sort(key=lambda item: item[0])
        unique_unsicherheiten: List[str] = []
        for _, text in uncertainties:
            if text not in unique_unsicherheiten:
                unique_unsicherheiten.append(text)

        next_steps: List[str] = []
        fallback_steps = [
            "Normenlage prüfen",
            "Betriebsgrenzen verifizieren",
            "Kosten/Nutzen bewerten",
        ]
        for step in payload.get("naechste_schritte", []) or []:
            if isinstance(step, str) and step.strip():
                next_steps.append(step.strip())
        if not next_steps:
            next_steps = fallback_steps[:]

        return {
            "schema_version": payload.get("schema_version") or "1.0.0",
            "empfehlung": recommendation,
            "alternativen": alternativen,
            "unsicherheiten": unique_unsicherheiten,
            "naechste_schritte": next_steps,
        }


__all__ = ["SyntheseNode"]
