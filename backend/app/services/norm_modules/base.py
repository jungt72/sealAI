from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


NormCheckContext = Mapping[str, Any]


class NormCheckStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_DATA = "insufficient_data"
    PASS = "pass"
    REVIEW_REQUIRED = "review_required"
    FAIL = "fail"


class EscalationPolicy(str, Enum):
    NO_ESCALATION = "no_escalation"
    REQUIRE_MANUFACTURER_REVIEW = "require_manufacturer_review"
    BLOCK_UNTIL_MISSING_FIELDS = "block_until_missing_fields"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True, slots=True)
class NormCheckFinding:
    code: str
    message: str
    severity: str = "info"
    field: str | None = None


@dataclass(frozen=True, slots=True)
class NormCheckResult:
    module_id: str
    version: str
    status: NormCheckStatus
    applies: bool
    missing_required_fields: tuple[str, ...] = ()
    findings: tuple[NormCheckFinding, ...] = ()
    escalation: EscalationPolicy = EscalationPolicy.NO_ESCALATION
    references: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_blocking_issue(self) -> bool:
        return self.status in {
            NormCheckStatus.INSUFFICIENT_DATA,
            NormCheckStatus.FAIL,
        }


class NormModule(ABC):
    """Small deterministic contract for one independently activatable norm."""

    module_id: str
    version: str

    @abstractmethod
    def applies_to(self, context: NormCheckContext) -> bool:
        raise NotImplementedError

    @abstractmethod
    def required_fields(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def check(self, context: NormCheckContext) -> NormCheckResult:
        raise NotImplementedError

    @abstractmethod
    def escalation_policy(self) -> EscalationPolicy:
        raise NotImplementedError


def missing_fields(context: NormCheckContext, required_fields: list[str]) -> tuple[str, ...]:
    missing: list[str] = []
    for field_name in required_fields:
        value = context.get(field_name)
        if value is None or value == "":
            missing.append(field_name)
    return tuple(missing)


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
