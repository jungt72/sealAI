"""Validation helpers for unified LangGraph IO models."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Type, TypeVar

from pydantic import BaseModel

from .schema import (
    AgentInput,
    AgentOutput,
    DiscoveryOutput,
    HandoffSpec,
    IntentClassification,
    ParameterBag,
    SafetyVerdict,
    SynthesisOutput,
)

T = TypeVar("T", bound=BaseModel)


def _model_validate(model: Type[T], payload: Dict[str, Any]) -> T:
    validator = getattr(model, "model_validate", None)
    if callable(validator):  # pydantic v2
        return validator(payload)
    return model.parse_obj(payload)  # type: ignore[return-value]


def ensure_parameter_bag(payload: Dict[str, Any]) -> ParameterBag:
    return _model_validate(ParameterBag, payload)


def ensure_discovery(payload: Dict[str, Any]) -> DiscoveryOutput:
    return _model_validate(DiscoveryOutput, payload)


def ensure_intent(payload: Dict[str, Any]) -> IntentClassification:
    return _model_validate(IntentClassification, payload)


def ensure_handoff(payload: Dict[str, Any]) -> HandoffSpec:
    return _model_validate(HandoffSpec, payload)


def ensure_agent_input(payload: Dict[str, Any]) -> AgentInput:
    return _model_validate(AgentInput, payload)


def ensure_agent_output(payload: Dict[str, Any]) -> AgentOutput:
    return _model_validate(AgentOutput, payload)


def ensure_synthesis(payload: Dict[str, Any]) -> SynthesisOutput:
    return _model_validate(SynthesisOutput, payload)


def ensure_safety(payload: Dict[str, Any]) -> SafetyVerdict:
    return _model_validate(SafetyVerdict, payload)


def require_params(bag: ParameterBag, required: Sequence[str]) -> List[str]:
    missing: List[str] = []
    for name in required:
        if bag.get(name) is None:
            missing.append(name)
    return missing


__all__ = [
    "ensure_parameter_bag",
    "ensure_discovery",
    "ensure_intent",
    "ensure_handoff",
    "ensure_agent_input",
    "ensure_agent_output",
    "ensure_synthesis",
    "ensure_safety",
    "require_params",
]
