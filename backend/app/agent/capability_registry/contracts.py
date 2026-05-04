from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol


class CapabilityId(str, Enum):
    MEDIUM_INTELLIGENCE = "medium_intelligence"


class CapabilityKind(str, Enum):
    DOMAIN_CONTEXT = "domain_context"


FORBIDDEN_CAPABILITY_OUTPUT_TERMS: tuple[str, ...] = (
    "final freigegeben",
    "freigegeben",
    "garantiert geeignet",
    "garantiert bestaendig",
    "garantiert beständig",
    "final approved",
    "approved solution",
    "certified recommendation",
    "zertifiziert",
    "beste loesung",
    "beste lösung",
)


@dataclass(frozen=True, slots=True)
class CapabilitySafetyFlags:
    mutates_case_state: bool = False
    creates_engineering_truth: bool = False
    final_approval_claim_allowed: bool = False
    dispatch_allowed: bool = False
    external_contact_allowed: bool = False
    export_allowed: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "mutates_case_state": self.mutates_case_state,
            "creates_engineering_truth": self.creates_engineering_truth,
            "final_approval_claim_allowed": self.final_approval_claim_allowed,
            "dispatch_allowed": self.dispatch_allowed,
            "external_contact_allowed": self.external_contact_allowed,
            "export_allowed": self.export_allowed,
        }


@dataclass(frozen=True, slots=True)
class CapabilityInput:
    capability_id: CapabilityId | str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability_id": _enum_value(self.capability_id),
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: CapabilityId
    kind: CapabilityKind
    name: str
    version: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "capability_id": self.capability_id.value,
            "kind": self.kind.value,
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    capability_id: CapabilityId
    capability_kind: CapabilityKind
    input_summary: str
    candidate_facts: Mapping[str, Any] = field(default_factory=dict)
    context_notes: tuple[str, ...] = ()
    risk_notes: tuple[str, ...] = ()
    missing_field_hints: tuple[str, ...] = ()
    rfq_relevance_notes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    confidence: str | None = None
    validation_status: str = "unvalidated"
    safety: CapabilitySafetyFlags = field(default_factory=CapabilitySafetyFlags)
    output_contract_version: str = "capability_result_v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id.value,
            "capability_kind": self.capability_kind.value,
            "input_summary": self.input_summary,
            "candidate_facts": dict(self.candidate_facts),
            "context_notes": list(self.context_notes),
            "risk_notes": list(self.risk_notes),
            "missing_field_hints": list(self.missing_field_hints),
            "rfq_relevance_notes": list(self.rfq_relevance_notes),
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "validation_status": self.validation_status,
            "safety": self.safety.as_dict(),
            "output_contract_version": self.output_contract_version,
        }


class CapabilityOutputSafetyError(ValueError):
    pass


class CapabilityModule(Protocol):
    @property
    def descriptor(self) -> CapabilityDescriptor: ...

    def run(self, capability_input: CapabilityInput) -> CapabilityResult: ...


def assert_capability_output_safe(result: CapabilityResult) -> None:
    text = " ".join(_text_values(result.as_dict())).casefold()
    for term in FORBIDDEN_CAPABILITY_OUTPUT_TERMS:
        if term.casefold() in text:
            raise CapabilityOutputSafetyError(
                f"capability output contains forbidden term: {term}"
            )


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        items: list[str] = []
        for key, item in value.items():
            items.extend(_text_values(key))
            items.extend(_text_values(item))
        return items
    if isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            items.extend(_text_values(item))
        return items
    if value is None:
        return []
    return [str(value)]


def _enum_value(value: CapabilityId | CapabilityKind | str) -> str:
    return str(getattr(value, "value", value))
