"""Adapter helpers to integrate legacy agents with the unified IO models."""
from __future__ import annotations

from typing import Any, Dict, Iterable

from app.langgraph.io.schema import AgentInput, AgentOutput, ParamValue
from app.langgraph.io.units import normalize_bag
from app.langgraph.io.validation import ensure_agent_input, ensure_agent_output, ensure_parameter_bag


def _export_model(model: Any) -> Dict[str, Any]:
    exporter = getattr(model, "model_dump", None)
    if callable(exporter):
        return exporter()
    to_dict = getattr(model, "dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(model, dict):
        return dict(model)
    return {}


def adapt_agent_input(payload: Dict[str, Any]) -> AgentInput:
    """Normalize a loose payload into an `AgentInput` model."""
    bag_source = payload.get("parameter") or payload.get("eingaben") or payload.get("parameter_bag") or {}
    bag = ensure_parameter_bag(bag_source if isinstance(bag_source, dict) else {"items": bag_source})
    canonical = normalize_bag(bag)

    data = {
        "schema_version": payload.get("schema_version"),
        "ziel": payload.get("ziel") or payload.get("auftrag") or "Beratung",
        "parameter": _export_model(canonical),
        "constraints": payload.get("constraints") or payload.get("restriktionen") or [],
    }
    return ensure_agent_input(data)


def build_legacy_agent_state(agent_input: AgentInput, *, base: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Convert an `AgentInput` into the dict structure expected by legacy agents."""
    state: Dict[str, Any] = dict(base or {})
    params: Dict[str, Any] = dict(state.get("params") or {})

    bag = agent_input.parameter
    items: Iterable[ParamValue]
    exporter = getattr(bag, "model_dump", None)
    if callable(exporter):
        raw = exporter()
    else:
        raw = bag.dict()  # type: ignore[call-arg]
    items = raw.get("items", []) if isinstance(raw, dict) else []

    for item in items:
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
        value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
        if not name:
            continue
        params[name] = value

    state["params"] = params
    state.setdefault("ziel", agent_input.ziel)
    state.setdefault(
        "constraints",
        [
            _export_model(c)
            for c in getattr(agent_input, "constraints", [])
        ],
    )
    return state


def adapt_agent_output(payload: Dict[str, Any] | AgentOutput) -> Dict[str, Any]:
    """Convert legacy agent results to the unified `AgentOutput` dict form."""
    if isinstance(payload, AgentOutput):
        model = payload
    else:
        model = ensure_agent_output(payload)
    return _export_model(model)


__all__ = ["adapt_agent_input", "build_legacy_agent_state", "adapt_agent_output"]
