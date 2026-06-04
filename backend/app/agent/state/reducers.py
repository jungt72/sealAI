"""
Deterministic State Reducers — Phase F-B.2

Every state transition is an explicit, pure, testable function.
No hidden writes. No LLM calls. No I/O.

Transition chain:
  ObservedState
      ↓ reduce_observed_to_normalized()
  NormalizedState
      ↓ reduce_normalized_to_asserted(evidence)
  AssertedState
      ↓ reduce_asserted_to_governance()
  GovernanceState

Architecture rule (Umbauplan F-B.2):
  These are the ONLY functions that may produce NormalizedState,
  AssertedState, or GovernanceState instances. Call-site code that
  constructs these models directly is an architecture violation.

Evidence type (Claim):
  A minimal claim contract is defined here. The full evidence layer
  (Phase G/H) will provide richer Claim objects — they must satisfy
  this protocol to be accepted by reduce_normalized_to_asserted().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from app.agent.domain.requirement_class import (
    RequirementClassSpecialistInput,
    run_requirement_class_specialist,
)
from app.agent.domain.normalization import (
    MappingConfidence,
    normalize_critical_field_value,
    normalize_parameter,
    pressure_field_for_interpretation,
)
from app.agent.domain.medium_registry import is_medium_placeholder_value
from app.services.conflict_detection_service import (
    ConflictCandidate,
    ConflictDetectionService,
)
from app.domain.critical_field_contract import PRESSURE_FIELDS
from app.domain.seal_packs import state_gate_type_sensitive_fields_for

from app.agent.state.models import (
    AssertedClaim,
    CaseField,
    AssertedState,
    AssumptionRef,
    ConflictRef,
    ConfidenceLevel,
    DecisionState,
    EngineeringValue,
    FieldStatus,
    GovernanceState,
    GovernedSessionState,
    GovClass,
    NormalizedParameter,
    NormalizedState,
    ObservedState,
    RequirementClass,
    UserOverride,
)

log = logging.getLogger(__name__)


DEPENDENCY_MAP: dict[str, list[str]] = {
    "temperature_max": ["material_suitability", "requirement_class", "preselection"],
    "temperature_c": ["material_suitability", "requirement_class", "preselection"],
    "medium": ["material_suitability", "requirement_class", "applicable_norms"],
    "medium_qualifiers": [
        "material_suitability",
        "requirement_class",
        "applicable_norms",
        "preselection",
    ],
    "rpm": ["pv_value", "velocity", "material_suitability"],
    "shaft_diameter": ["pv_value", "velocity"],
    "shaft_diameter_mm": ["pv_value", "velocity"],
    "pressure": ["requirement_class", "material_suitability"],
    "pressure_bar": ["requirement_class", "material_suitability"],
    "medium_confidence": ["material_suitability"],
    "sealing_type": ["requirement_class", "preselection"],
    "pressure_direction": ["requirement_class", "preselection"],
    "duty_profile": ["requirement_class", "preselection"],
    "installation": ["requirement_class", "preselection"],
    "geometry_context": ["requirement_class", "preselection"],
    "contamination": ["material_suitability", "requirement_class", "preselection"],
    "contamination_condition": [
        "material_suitability",
        "requirement_class",
        "preselection",
    ],
    "counterface_surface": [
        "material_suitability",
        "requirement_class",
        "preselection",
    ],
    "counterface_surface_condition": [
        "material_suitability",
        "requirement_class",
        "preselection",
    ],
    "shaft_roughness_ra_um": ["material_suitability", "requirement_class", "preselection"],
    "shaft_hardness_hrc": ["material_suitability", "requirement_class", "preselection"],
    "runout_mm": ["material_suitability", "requirement_class", "preselection"],
    "eccentricity_mm": ["material_suitability", "requirement_class", "preselection"],
    "axial_movement_mm": ["material_suitability", "requirement_class", "preselection"],
    "lubrication_condition": ["material_suitability", "requirement_class", "preselection"],
    "installation_space_summary": ["requirement_class", "preselection"],
    "tolerances": ["material_suitability", "requirement_class", "preselection"],
    "industry": ["requirement_class", "applicable_norms", "preselection"],
    "compliance": ["requirement_class", "applicable_norms", "preselection"],
}


def _float_to_confidence(value: float) -> ConfidenceLevel:
    """Map a numeric LLM confidence score (0.0–1.0) to a ConfidenceLevel string.

    Thresholds (Umbauplan F-B.2):
      ≥ 0.90 → confirmed
      ≥ 0.70 → estimated
      ≥ 0.50 → inferred
       < 0.50 → requires_confirmation
    """
    if value >= 0.90:
        return "confirmed"
    if value >= 0.70:
        return "estimated"
    if value >= 0.50:
        return "inferred"
    return "requires_confirmation"


def _extraction_confidence(e: Any) -> ConfidenceLevel:
    """Return the ConfidenceLevel for an ObservedExtraction.

    ObservedExtraction.confidence is a float (0.0–1.0).
    Accepts str for forward-compatibility with Phase G evidence layer.
    """
    c = e.confidence
    if isinstance(c, str):
        return (
            c
            if c in ("confirmed", "estimated", "inferred", "requires_confirmation")
            else "requires_confirmation"
        )
    try:
        return _float_to_confidence(float(c))
    except (TypeError, ValueError):
        return "requires_confirmation"


# ---------------------------------------------------------------------------
# Core required fields for governance
# ---------------------------------------------------------------------------

# Minimum set of fields that must be asserted at CONFIRMED or ESTIMATED
# confidence before Class A governance is reachable.
_CORE_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "medium",
        "pressure_bar",
        "temperature_c",
    }
)

_PRESELECTION_BLOCKER_BASE_FIELDS: tuple[str, ...] = (
    "medium",
    "pressure_bar",
    "temperature_c",
    "sealing_type",
)

_PRESSURE_DESIGN_FIELDS: tuple[str, ...] = (
    "pressure_at_seal_bar",
    "pressure_delta_bar",
)
_PRESSURE_ROLE_FIELDS: tuple[str, ...] = (
    "pressure_system_bar",
    "pressure_at_seal_bar",
    "pressure_delta_bar",
)

_ASSUMABLE_FIELDS: tuple[str, ...] = (
    "pressure_direction",
    "contamination",
    "counterface_surface",
    "tolerances",
    "medium_qualifiers",
)

_OPTIONAL_CONTEXT_FIELDS: tuple[str, ...] = ("industry",)

# Per-seal-type type-sensitive required fields are owned by the domain layer
# (`app/domain/seal_packs.py::state_gate_type_sensitive_fields_for` — RWDR via
# the pack, others as shallow stubs). The core no longer hardcodes a per-type
# field dict (P1-4 PR1; CORE_PACK_BOUNDARY.md:13).

_ROTARY_CONTEXT_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_diameter_mm",
        "speed_rpm",
    }
)

_REGULATED_INDUSTRIES: frozenset[str] = frozenset(
    {
        "food_pharma",
    }
)

_REGULATORY_COMPLIANCE_VALUES: frozenset[str] = frozenset(
    {
        "food_contact",
        "atex",
        "norm_or_regulatory",
    }
)

# §12.6: a value conflict degrades to a field-level open point (Class B) instead
# of blocking the whole case. A conflict is only kept hard-blocking (Class C)
# when it touches a safety-/compliance-critical field. Conservative by design —
# in a regulated context (active compliance_blockers) any conflict stays blocking.
_SAFETY_CONFLICT_FIELDS: frozenset[str] = frozenset({"compliance"})

# Fields at INFERRED or REQUIRES_CONFIRMATION confidence → blocking_unknowns
_BLOCKING_CONFIDENCE_LEVELS: frozenset[ConfidenceLevel] = frozenset(
    {
        "requires_confirmation",
    }
)

# Fields at these confidence levels may be asserted (with caveats)
_ASSERTABLE_CONFIDENCE_LEVELS: frozenset[ConfidenceLevel] = frozenset(
    {
        "confirmed",
        "estimated",
        "inferred",
    }
)


def _asserted_value(assertions: dict[str, AssertedClaim], field_name: str) -> Any:
    claim = assertions.get(field_name)
    return None if claim is None else claim.asserted_value


def _value_contains(value: Any, needle: str) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(_value_contains(item, needle) for item in value)
    return str(value or "").strip().casefold() == needle.casefold()


def _has_asserted(assertions: dict[str, AssertedClaim], field_name: str) -> bool:
    return _asserted_value(assertions, field_name) not in (None, "")


def _missing(
    assertions: dict[str, AssertedClaim], fields: tuple[str, ...]
) -> list[str]:
    missing: list[str] = []
    for field_name in fields:
        if field_name == "pressure_bar" and _has_design_pressure(assertions):
            continue
        if not _has_asserted(assertions, field_name):
            missing.append(field_name)
    return missing


def _has_design_pressure(assertions: dict[str, AssertedClaim]) -> bool:
    return any(_has_asserted(assertions, field) for field in _PRESSURE_DESIGN_FIELDS)


@dataclass(frozen=True)
class TechnicalReadinessAssessment:
    preselection_blockers: list[str] = field(default_factory=list)
    missing_but_assumable: list[str] = field(default_factory=list)
    optional_context: list[str] = field(default_factory=list)
    compliance_blockers: list[str] = field(default_factory=list)
    type_sensitive_required: list[str] = field(default_factory=list)


def _technical_readiness_assessment(
    asserted: AssertedState,
) -> TechnicalReadinessAssessment:
    assertions = asserted.assertions
    blockers = _missing(assertions, _PRESELECTION_BLOCKER_BASE_FIELDS)
    type_sensitive: list[str] = []

    sealing_type = str(_asserted_value(assertions, "sealing_type") or "").strip()
    type_sensitive_fields = state_gate_type_sensitive_fields_for(sealing_type)
    if type_sensitive_fields is not None:
        type_sensitive.extend(_missing(assertions, type_sensitive_fields))
    elif (
        any(_has_asserted(assertions, field) for field in _ROTARY_CONTEXT_FIELDS)
        and "sealing_type" not in blockers
    ):
        blockers.append("sealing_type")

    industry = _asserted_value(assertions, "industry")
    compliance = _asserted_value(assertions, "compliance")
    compliance_blockers: list[str] = []
    if any(_value_contains(industry, item) for item in _REGULATED_INDUSTRIES):
        if not any(
            _value_contains(compliance, item) for item in _REGULATORY_COMPLIANCE_VALUES
        ):
            compliance_blockers.append("compliance")

    missing_but_assumable = _missing(assertions, _ASSUMABLE_FIELDS)
    optional_context = _missing(assertions, _OPTIONAL_CONTEXT_FIELDS)

    return TechnicalReadinessAssessment(
        preselection_blockers=list(
            dict.fromkeys(blockers + type_sensitive + compliance_blockers)
        ),
        missing_but_assumable=missing_but_assumable,
        optional_context=optional_context,
        compliance_blockers=compliance_blockers,
        type_sensitive_required=list(dict.fromkeys(type_sensitive)),
    )


# ---------------------------------------------------------------------------
# Evidence protocol (minimal — full implementation in Phase G evidence layer)
# ---------------------------------------------------------------------------


class Claim(Protocol):
    """Protocol for evidence claims accepted by reduce_normalized_to_asserted."""

    @property
    def claim_id(self) -> str: ...

    @property
    def field_name(self) -> str: ...

    @property
    def value(self) -> Any: ...

    @property
    def confidence(self) -> ConfidenceLevel: ...


def _field_status_for_normalized(
    *,
    source: str,
    confidence: ConfidenceLevel,
) -> FieldStatus:
    if source == "user_override":
        return "confirmed"
    if confidence == "confirmed":
        return "user_stated"
    if confidence == "requires_confirmation":
        return "candidate"
    if confidence == "inferred":
        return "inferred"
    return "candidate"


def _provenance_for_normalized(*, source: str, confidence: ConfidenceLevel) -> str:
    if source == "user_override":
        return "user_stated"
    if confidence == "inferred":
        return "inferred"
    return "user_stated"


def _engineering_value(
    *,
    field_name: str,
    raw_value: Any,
    value: Any,
    unit: str | None,
    raw_unit: str | None = None,
) -> EngineeringValue:
    normalized = normalize_critical_field_value(
        field_name,
        raw_value,
        unit=raw_unit if raw_unit is not None else unit,
    )
    if normalized is not None:
        return EngineeringValue(**normalized.as_engineering_value_dict())
    return EngineeringValue(
        raw_value=raw_value,
        canonical_value=value,
        unit=unit,
        quantity_kind=field_name,
    )


def _normalize_case_field_value(
    *,
    field_name: str,
    raw_value: Any,
    unit: str | None,
    confidence: ConfidenceLevel,
) -> tuple[Any, str | None, ConfidenceLevel]:
    if field_name == "medium":
        normalized_medium = normalize_parameter("medium", raw_value)
        if normalized_medium.normalized_value in (None, ""):
            return None, None, "requires_confirmation"
        return normalized_medium.normalized_value, None, confidence

    normalized = normalize_critical_field_value(field_name, raw_value, unit=unit)
    if normalized is None:
        return raw_value, unit, confidence
    normalized_confidence = (
        "requires_confirmation"
        if normalized.confidence == MappingConfidence.REQUIRES_CONFIRMATION
        else confidence
    )
    return normalized.canonical_value, normalized.unit, normalized_confidence


def _case_field_from_normalized(
    *,
    field_name: str,
    value: Any,
    raw_value: Any,
    unit: str | None,
    raw_unit: str | None = None,
    confidence: ConfidenceLevel,
    source: str,
    source_turn: int | None,
) -> CaseField:
    status = _field_status_for_normalized(source=source, confidence=confidence)
    if field_name == "medium" and is_medium_placeholder_value(str(raw_value or "")):
        status = "invalid"
    provenance = _provenance_for_normalized(source=source, confidence=confidence)
    return CaseField(
        field_name=field_name,
        value=value,
        engineering_value=_engineering_value(
            field_name=field_name,
            raw_value=raw_value,
            value=value,
            unit=unit,
            raw_unit=raw_unit,
        ),
        status=status,
        provenance=provenance,
        confidence=confidence,
        confirmation_required=status in {"candidate", "inferred", "unknown", "invalid"},
        source_revision=source_turn or 0,
    )


def _asserted_case_field(
    *,
    field_name: str,
    value: Any,
    unit: str | None,
    confidence: ConfidenceLevel,
    evidence_refs: list[str],
    provenance: str,
    status: FieldStatus = "confirmed",
    confirmation_required: bool = False,
) -> CaseField:
    return CaseField(
        field_name=field_name,
        value=value,
        engineering_value=_engineering_value(
            field_name=field_name,
            raw_value=value,
            value=value,
            unit=unit,
            raw_unit=unit,
        ),
        status=status,
        provenance=provenance,
        evidence_refs=evidence_refs,
        confidence=confidence,
        confirmation_required=confirmation_required,
    )


def _conflict_assertion(
    *,
    field_name: str,
    value: Any,
    unit: str | None,
    provenance: str = "user_stated",
) -> AssertedClaim:
    """Build a field-level conflict claim (§12.6).

    Marks the field FieldStatus ``"conflict"`` at ``requires_confirmation`` so it
    surfaces as an open point and is rejected by EvidenceConfirmationIntelligence
    (``_BLOCKING_FIELD_STATUSES``). It never counts as a confirmed core field and
    must not drive deterministic calculations.
    """
    case_field = _asserted_case_field(
        field_name=field_name,
        value=value,
        unit=unit,
        confidence="requires_confirmation",
        evidence_refs=[],
        provenance=provenance,
        status="conflict",
        confirmation_required=True,
    )
    return AssertedClaim(
        field_name=field_name,
        asserted_value=value,
        evidence_refs=[],
        confidence="requires_confirmation",
        status="conflict",
        provenance=case_field.provenance,
        engineering_value=case_field.engineering_value,
        case_field=case_field,
    )


def _is_user_accepted_pressure_value(param: NormalizedParameter) -> bool:
    """Treat an accepted numeric pressure as a usable value, not a missing field.

    A bare "5 bar" can still have unknown interpretation (gauge/absolute/
    differential/direct-at-seal), but once the user accepts the value it should
    drive deterministic prechecks. The interpretation remains a validation
    point in governance instead of making pressure_bar disappear from asserted
    state.
    """
    if param.source != "user_override" or param.field_name not in PRESSURE_FIELDS:
        return False
    if param.value in (None, "", [], {}):
        return False
    engineering_value = param.engineering_value
    return (
        engineering_value.quantity_kind == "pressure"
        and engineering_value.canonical_value not in (None, "", [], {})
        and engineering_value.interpretation == "unknown"
    )


_DIRECT_USER_STATED_CALCULATION_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_diameter_mm",
        "speed_rpm",
        "rpm",
        "rotational_speed_rpm",
        "housing_bore_mm",
        "installation_width_mm",
        "seal_width_mm",
        "oring_cross_section_mm",
        "cord_diameter_mm",
        "schnurdurchmesser_mm",
        "cross_section_mm",
        "groove_depth_mm",
        "nuttiefe_mm",
        "groove_width_mm",
        "nutbreite_mm",
        "seal_inner_diameter_mm",
        "oring_inner_diameter_mm",
        "o_ring_inner_diameter_mm",
        "rod_diameter_mm",
        "bore_diameter_mm",
        "radial_gap_mm",
        "sealing_type",
        "seal_type",
        "motion_type",
        "movement_type",
        "installation",
        "duty_profile",
        "geometry_context",
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "pressure_system_bar",
        "shaft_roughness_ra_um",
        "surface_roughness_ra_um",
        "shaft_hardness_hrc",
        "surface_hardness_hrc",
        "runout_mm",
        "eccentricity_mm",
        "axial_movement_mm",
        "lubrication_condition",
        "contamination_condition",
        "installation_space_summary",
    }
)

_CASE_CONTEXT_FOR_USER_STATED_CALCULATIONS: frozenset[str] = frozenset(
    {
        "sealing_type",
        "seal_type",
        "motion_type",
        "movement_type",
        "installation",
        "shaft_diameter_mm",
        "speed_rpm",
        "oring_cross_section_mm",
        "groove_depth_mm",
        "groove_width_mm",
    }
)

_CONTEXTUAL_USER_STATED_CALCULATION_FIELDS: frozenset[str] = frozenset(
    {
        "temperature_c",
        "temperature_max_c",
        "material",
        "material_family",
        "sealing_material_family",
        "compound_family",
    }
)


def _should_promote_user_stated_calculation_input(
    field_name: str,
    param: NormalizedParameter,
    *,
    normalized_field_names: set[str],
) -> bool:
    """Promote explicit chat values only when they are safe calculator inputs.

    This is intentionally narrower than "any confirmed LLM extraction": free
    dialogue can contain acknowledgements, examples or knowledge terms that must
    not become case facts. Numeric/geometric inputs and clearly typed case
    context are safe to promote; bare pressure_bar still requires role
    clarification unless it came from an explicit UI override.
    """
    if param.source != "llm":
        return False
    if param.confidence != "confirmed":
        return False
    if param.value in (None, "", [], {}):
        return False
    if field_name in {"pressure_bar", "ambiguous_pressure_bar"}:
        return False
    if field_name in _DIRECT_USER_STATED_CALCULATION_FIELDS:
        return True
    if field_name in _CONTEXTUAL_USER_STATED_CALCULATION_FIELDS:
        return bool(normalized_field_names & _CASE_CONTEXT_FOR_USER_STATED_CALCULATIONS)
    return False


@dataclass(frozen=True)
class SimpleClaim:
    """Concrete minimal claim for testing and internal use.

    Phase G evidence layer will provide its own Claim implementation.
    """

    claim_id: str
    field_name: str
    value: Any
    confidence: ConfidenceLevel = "confirmed"


# ---------------------------------------------------------------------------
# F-B.2.1 — reduce_observed_to_normalized
# ---------------------------------------------------------------------------


def reduce_observed_to_normalized(observed: ObservedState) -> NormalizedState:
    """Derive NormalizedState from ObservedState.

    Rules (deterministic, no LLM):
    1. User overrides always win for the same field_name.
    2. Among LLM extractions for the same field, highest confidence wins.
       Ties broken by latest turn_index (most recent extraction).
    3. Multiple LLM extractions with significantly different values
       (not merely different confidence) → ConflictRef(severity='warning').
    4. Parameters with confidence 'requires_confirmation' → AssumptionRef.
    5. Parameters with confidence 'confirmed'/'estimated'/'inferred' → NormalizedParameter.

    Returns a new NormalizedState. Never mutates the input.
    """
    # ── Step 1: index user overrides (last override per field wins) ───────
    override_by_field: dict[str, UserOverride] = {}
    for override in observed.user_overrides:
        override_by_field[override.field_name] = override  # latest wins

    # ── Step 2: group LLM extractions by field ────────────────────────────
    extractions_by_field: dict[str, list] = {}
    for ext in observed.raw_extractions:
        if ext.source in ("llm", "user"):
            extractions_by_field.setdefault(ext.field_name, []).append(ext)

    # ── Step 3: resolve parameters ───────────────────────────────────────
    conflict_detector = ConflictDetectionService()
    parameters: dict[str, NormalizedParameter] = {}
    conflicts: list[ConflictRef] = []
    assumptions: list[AssumptionRef] = []
    parameter_status: dict[str, str] = {}

    # Collect all field names from both overrides and extractions
    all_fields = set(override_by_field) | set(extractions_by_field)

    for field_name in all_fields:
        # User override takes absolute priority
        if field_name in override_by_field:
            ov = override_by_field[field_name]
            normalized_value, normalized_unit, normalized_confidence = (
                _normalize_case_field_value(
                    field_name=field_name,
                    raw_value=ov.override_value,
                    unit=ov.override_unit,
                    confidence="confirmed",
                )
            )
            case_field = _case_field_from_normalized(
                field_name=field_name,
                value=normalized_value,
                raw_value=ov.override_value,
                unit=normalized_unit,
                raw_unit=ov.override_unit,
                confidence=normalized_confidence,
                source="user_override",
                source_turn=ov.turn_index,
            )
            parameters[field_name] = NormalizedParameter(
                field_name=field_name,
                value=normalized_value,
                unit=normalized_unit,
                confidence=normalized_confidence,
                source="user_override",
                source_turn=ov.turn_index,
                status=case_field.status,
                provenance=case_field.provenance,
                engineering_value=case_field.engineering_value,
                case_field=case_field,
            )
            parameter_status[field_name] = "observed"
            log.debug(
                "[reducer] field=%s source=user_override value=%r",
                field_name,
                normalized_value,
            )
            continue

        exts = extractions_by_field.get(field_name, [])
        if not exts:
            continue

        # Sort by confidence (desc) then turn_index (desc — more recent wins ties)
        _CONF_RANK = {
            "confirmed": 4,
            "estimated": 3,
            "inferred": 2,
            "requires_confirmation": 1,
        }
        exts_sorted = sorted(
            exts,
            key=lambda e: (_CONF_RANK.get(_extraction_confidence(e), 0), e.turn_index),
            reverse=True,
        )
        best = exts_sorted[0]

        conflict_result = conflict_detector.detect_observed_candidates(
            field_name,
            [
                ConflictCandidate(
                    field_name=field_name,
                    value=e.raw_value,
                    provenance=e.source,
                    source_turn_index=e.turn_index,
                )
                for e in exts
            ],
        )
        for detected in conflict_result.conflicts:
            conflicts.append(
                ConflictRef(
                    field_name=field_name,
                    description=detected.description,
                    severity=detected.severity,
                )
            )
            log.debug(
                "[reducer] conflict detected for field=%s current=%r candidate=%r",
                field_name,
                detected.current_value,
                detected.candidate_value,
            )

        # Confidence grade of the best extraction
        confidence: ConfidenceLevel = _extraction_confidence(best)
        normalized_value, normalized_unit, confidence = _normalize_case_field_value(
            field_name=field_name,
            raw_value=best.raw_value,
            unit=best.raw_unit,
            confidence=confidence,
        )

        if confidence == "requires_confirmation":
            assumptions.append(
                AssumptionRef(
                    field_name=field_name,
                    description=f"'{field_name}' requires user confirmation (value: {best.raw_value!r})",
                )
            )
            parameter_status[field_name] = "assumed"
        else:
            parameter_status[field_name] = "observed"

        case_field = _case_field_from_normalized(
            field_name=field_name,
            value=normalized_value,
            raw_value=best.raw_value,
            unit=normalized_unit,
            raw_unit=best.raw_unit,
            confidence=confidence,
            source="llm",
            source_turn=best.turn_index,
        )
        parameters[field_name] = NormalizedParameter(
            field_name=field_name,
            value=normalized_value,
            unit=normalized_unit,
            confidence=confidence,
            source="llm",
            source_turn=best.turn_index,
            status=case_field.status,
            provenance=case_field.provenance,
            engineering_value=case_field.engineering_value,
            case_field=case_field,
        )

    _add_pressure_role_parameters(parameters, parameter_status)

    return NormalizedState(
        parameters=parameters,
        unit_system="SI",
        conflicts=conflicts,
        assumptions=assumptions,
        parameter_status=parameter_status,
        case_fields={
            field_name: param.case_field
            for field_name, param in parameters.items()
            if param.case_field is not None
        },
    )


def _add_pressure_role_parameters(
    parameters: dict[str, NormalizedParameter],
    parameter_status: dict[str, str],
) -> None:
    legacy = parameters.get("pressure_bar")
    if legacy is None or legacy.value in (None, ""):
        return

    engineering_value = legacy.engineering_value
    interpretation = str(getattr(engineering_value, "interpretation", "") or "").strip()
    target_field = pressure_field_for_interpretation(interpretation)
    confidence = legacy.confidence
    if target_field is None:
        if any(field in parameters for field in _PRESSURE_ROLE_FIELDS):
            return
        target_field = "ambiguous_pressure_bar"
        confidence = "requires_confirmation"

    if target_field in parameters:
        return

    case_field = _case_field_from_normalized(
        field_name=target_field,
        value=legacy.value,
        raw_value=getattr(engineering_value, "raw_value", legacy.value),
        unit="bar",
        raw_unit="bar",
        confidence=confidence,
        source=legacy.source,
        source_turn=legacy.source_turn,
    )
    parameters[target_field] = NormalizedParameter(
        field_name=target_field,
        value=legacy.value,
        unit="bar",
        confidence=confidence,
        source=legacy.source,
        source_turn=legacy.source_turn,
        status=case_field.status,
        provenance=case_field.provenance,
        engineering_value=case_field.engineering_value,
        case_field=case_field,
    )
    parameter_status[target_field] = parameter_status.get("pressure_bar", "observed")


def _canonical_value(v: Any) -> str:
    """Collapse a value to a canonical string for conflict detection."""
    if v is None:
        return "None"
    s = str(v).strip().lower()
    return s


# ---------------------------------------------------------------------------
# F-B.2.2 — reduce_normalized_to_asserted
# ---------------------------------------------------------------------------


def reduce_normalized_to_asserted(
    normalized: NormalizedState,
    evidence: list[Claim] | None = None,
) -> AssertedState:
    """Derive AssertedState from NormalizedState and optional evidence claims.

    Rules (deterministic):
    1. Normalized candidates from LLM/regex extraction are not asserted by
       confidence alone.
    2. User overrides are explicit promotion and may become AssertedClaim.
    3. Explicit user-stated, unambiguous calculation inputs may be promoted so
       deterministic calculators can run from chat intake without UI overrides.
    4. Matching confirmed/estimated evidence claims may promote a candidate.
    5. Parameters at 'requires_confirmation' → blocking_unknowns.
    6. Blocking ConflictRefs → conflict_flags.
    7. Core required fields that are absent entirely → blocking_unknowns.

    Returns a new AssertedState. Never mutates inputs.
    """
    evidence = evidence or []

    # Build evidence index: field_name → best claim
    evidence_index: dict[str, Claim] = {}
    _CONF_RANK = {
        "confirmed": 4,
        "estimated": 3,
        "inferred": 2,
        "requires_confirmation": 1,
    }
    for claim in evidence:
        existing = evidence_index.get(claim.field_name)
        if existing is None or _CONF_RANK.get(claim.confidence, 0) > _CONF_RANK.get(
            existing.confidence, 0
        ):
            evidence_index[claim.field_name] = claim

    assertions: dict[str, AssertedClaim] = {}
    blocking_unknowns: list[str] = []
    conflict_flags: list[str] = []
    normalized_field_names = set(normalized.parameters)

    # ── Process normalized parameters ────────────────────────────────────
    for field_name, param in normalized.parameters.items():
        confidence = param.confidence
        ev = evidence_index.get(field_name)

        pressure_value_accepted = _is_user_accepted_pressure_value(param)
        if confidence == "requires_confirmation" and not pressure_value_accepted:
            blocking_unknowns.append(field_name)
            continue

        if param.source == "user_override":
            assertion_confidence: ConfidenceLevel = (
                "confirmed" if pressure_value_accepted else confidence
            )
            if param.case_field is not None:
                asserted_case_field = param.case_field.model_copy(
                    update={
                        "confidence": assertion_confidence,
                        "status": "confirmed",
                        "confirmation_required": False,
                        "evidence_refs": [],
                        "provenance": "user_stated",
                    }
                )
            else:
                asserted_case_field = _asserted_case_field(
                    field_name=field_name,
                    value=param.value,
                    unit=param.unit,
                    confidence=assertion_confidence,
                    evidence_refs=[],
                    provenance="user_stated",
                )
            assertions[field_name] = AssertedClaim(
                field_name=field_name,
                asserted_value=param.value,
                evidence_refs=[],
                confidence=assertion_confidence,
                status=asserted_case_field.status,
                provenance=asserted_case_field.provenance,
                engineering_value=asserted_case_field.engineering_value,
                case_field=asserted_case_field,
            )
            continue

        if _should_promote_user_stated_calculation_input(
            field_name,
            param,
            normalized_field_names=normalized_field_names,
        ):
            if param.case_field is not None:
                asserted_case_field = param.case_field.model_copy(
                    update={
                        "confidence": "confirmed",
                        "status": "confirmed",
                        "confirmation_required": False,
                        "evidence_refs": [],
                        "provenance": "user_stated",
                    }
                )
            else:
                asserted_case_field = _asserted_case_field(
                    field_name=field_name,
                    value=param.value,
                    unit=param.unit,
                    confidence="confirmed",
                    evidence_refs=[],
                    provenance="user_stated",
                )
            assertions[field_name] = AssertedClaim(
                field_name=field_name,
                asserted_value=param.value,
                evidence_refs=[],
                confidence="confirmed",
                status=asserted_case_field.status,
                provenance=asserted_case_field.provenance,
                engineering_value=asserted_case_field.engineering_value,
                case_field=asserted_case_field,
            )
            continue

        if ev is None or ev.confidence not in ("confirmed", "estimated"):
            log.debug(
                "[reducer] candidate_not_asserted field=%s source=%s confidence=%s",
                field_name,
                param.source,
                confidence,
            )
            continue

        if _canonical_value(ev.value) != _canonical_value(param.value):
            if field_name not in conflict_flags:
                conflict_flags.append(field_name)
            # §12.6: keep the field as a conflict open point, never as a
            # confirmed value. requires_confirmation excludes it from core_asserted.
            assertions[field_name] = _conflict_assertion(
                field_name=field_name,
                value=param.value,
                unit=param.unit,
            )
            log.debug(
                "[reducer] evidence_value_conflict field=%s candidate=%r evidence=%r claim=%s",
                field_name,
                param.value,
                ev.value,
                ev.claim_id,
            )
            continue

        asserted_case_field = _asserted_case_field(
            field_name=field_name,
            value=param.value,
            unit=param.unit,
            confidence=ev.confidence,
            evidence_refs=[ev.claim_id],
            provenance="documented",
        )
        assertions[field_name] = AssertedClaim(
            field_name=field_name,
            asserted_value=param.value,
            evidence_refs=[ev.claim_id],
            confidence=ev.confidence,
            status=asserted_case_field.status,
            provenance=asserted_case_field.provenance,
            engineering_value=asserted_case_field.engineering_value,
            case_field=asserted_case_field,
        )

    # ── Conflict flags from blocking conflicts ───────────────────────────
    for conflict in normalized.conflicts:
        if conflict.severity != "blocking":
            continue
        if conflict.field_name not in conflict_flags:
            conflict_flags.append(conflict.field_name)
        # §12.6: mark the field as a conflict open point unless it is already an
        # asserted (e.g. user-confirmed) value — never overwrite a confirmed value.
        if conflict.field_name not in assertions:
            param = normalized.parameters.get(conflict.field_name)
            assertions[conflict.field_name] = _conflict_assertion(
                field_name=conflict.field_name,
                value=getattr(param, "value", None),
                unit=getattr(param, "unit", None),
            )

    # ── Core fields missing entirely → blocking unknowns ─────────────────
    for core_field in _CORE_REQUIRED_FIELDS:
        if core_field == "pressure_bar" and _has_design_pressure(assertions):
            continue
        if core_field not in assertions and core_field not in blocking_unknowns:
            blocking_unknowns.append(core_field)

    readiness = _technical_readiness_assessment(
        AssertedState(
            assertions=assertions,
            blocking_unknowns=blocking_unknowns,
            conflict_flags=conflict_flags,
        )
    )
    for blocker in readiness.preselection_blockers:
        if blocker not in blocking_unknowns:
            blocking_unknowns.append(blocker)

    return AssertedState(
        assertions=assertions,
        blocking_unknowns=sorted(set(blocking_unknowns)),
        conflict_flags=sorted(set(conflict_flags)),
    )


# ---------------------------------------------------------------------------
# F-B.2.3 — reduce_asserted_to_governance
# ---------------------------------------------------------------------------


def reduce_asserted_to_governance(
    asserted: AssertedState,
    *,
    analysis_cycle: int = 0,
    max_cycles: int = 3,
) -> GovernanceState:
    """Derive GovernanceState from AssertedState.

    Governance class rules (Umbauplan F-B + F-C.2):
      A — all core fields asserted at confirmed/estimated, no blocking unknowns,
          no conflict flags → rfq_admissible = True
      B — some core fields asserted, blocking unknowns exist but cycle < max
          → proceed with caveats, rfq_admissible = False
      C — blocking unknowns persist after max_cycles, OR unresolvable conflicts
          → auto-fallback Class C, rfq_admissible = False
      D — none of the core required fields are asserted at all
          → out of scope, rfq_admissible = False

    Returns a new GovernanceState. Never mutates inputs.
    """
    core_asserted = {
        f
        for f in _CORE_REQUIRED_FIELDS
        if f in asserted.assertions
        and asserted.assertions[f].confidence in ("confirmed", "estimated")
    }
    readiness = _technical_readiness_assessment(asserted)
    effective_blocking_unknowns = list(
        dict.fromkeys(
            list(asserted.blocking_unknowns) + list(readiness.preselection_blockers)
        )
    )
    has_blocking_unknowns = bool(effective_blocking_unknowns)
    cycle_exceeded = analysis_cycle >= max_cycles

    # ── Conflict split (§12.6): field value conflict vs safety/compliance ──
    # A conflict on a safety-/compliance-critical field — or any conflict while
    # the case sits in a regulated context (active compliance_blockers) — stays
    # hard-blocking. All other field value conflicts degrade to a field-level
    # open point and must not block the whole case.
    in_regulated_context = bool(readiness.compliance_blockers)
    safety_conflicts = [
        f
        for f in asserted.conflict_flags
        if f in _SAFETY_CONFLICT_FIELDS or in_regulated_context
    ]
    value_conflicts = [f for f in asserted.conflict_flags if f not in safety_conflicts]
    has_safety_conflicts = bool(safety_conflicts)
    has_value_conflicts = bool(value_conflicts)

    # ── Determine governance class ────────────────────────────────────────
    gov_class: GovClass

    if not core_asserted:
        # No core fields at all → out of scope
        gov_class = "D"
    elif cycle_exceeded and has_blocking_unknowns:
        # Cycle limit exceeded with unresolved unknowns → force Class C
        gov_class = "C"
    elif has_safety_conflicts:
        # Safety-/compliance-relevant conflict → still hard-block (Class C)
        gov_class = "C"
    elif (
        not has_blocking_unknowns
        and core_asserted >= _CORE_REQUIRED_FIELDS
        and not has_value_conflicts
    ):
        # All core fields asserted, no blockers, no conflict → Class A
        gov_class = "A"
    else:
        # Partial assertions / open points / value conflict → Class B
        # (RFQ admissible with open points, not a clean ready state)
        gov_class = "B"

    rfq_admissible = gov_class == "A"

    # ── Validity limits ───────────────────────────────────────────────────
    validity_limits: list[str] = []
    for field_name, claim in asserted.assertions.items():
        if claim.confidence == "estimated":
            validity_limits.append(
                f"'{field_name}' is estimated — manufacturer validation required."
            )
        elif claim.confidence == "inferred":
            validity_limits.append(
                f"'{field_name}' is inferred — confirm before RFQ dispatch."
            )

    # ── Open validation points ────────────────────────────────────────────
    open_validation_points: list[str] = list(effective_blocking_unknowns)
    if asserted.conflict_flags:
        open_validation_points += [
            f"Unresolved conflict: '{f}'" for f in asserted.conflict_flags
        ]
    for field_name, claim in asserted.assertions.items():
        engineering_value = claim.engineering_value
        if (
            field_name in PRESSURE_FIELDS
            and engineering_value.interpretation == "unknown"
        ):
            if "pressure_interpretation" not in open_validation_points:
                open_validation_points.append("pressure_interpretation")
            limit = (
                "'pressure_bar' value is user-stated, but pressure interpretation "
                "(gauge/absolute/differential/direct-at-seal) still requires "
                "manufacturer validation."
            )
            if limit not in validity_limits:
                validity_limits.append(limit)
    for item in readiness.missing_but_assumable:
        if item not in open_validation_points:
            open_validation_points.append(item)

    # ── Requirement class (minimal — Phase G will enrich this) ───────────
    requirement_class: Optional[RequirementClass] = None
    requirement_class_open_points: list[str] = []
    requirement_class_scope: list[str] = []
    if gov_class in ("A", "B"):
        requirement_result = run_requirement_class_specialist(
            RequirementClassSpecialistInput(asserted_state=asserted)
        )
        requirement_class = requirement_result.preferred_requirement_class
        requirement_class_open_points = list(requirement_result.open_points)
        requirement_class_scope = list(requirement_result.scope_of_validity)

    if gov_class == "B":
        for item in requirement_class_open_points:
            if item not in open_validation_points:
                open_validation_points.append(item)
        for item in requirement_class_scope:
            if item not in validity_limits:
                validity_limits.append(item)

    log.debug(
        "[reducer] governance class=%s rfq_admissible=%s "
        "core_asserted=%s blocking=%s conflicts=%s cycle=%d/%d",
        gov_class,
        rfq_admissible,
        sorted(core_asserted),
        asserted.blocking_unknowns,
        asserted.conflict_flags,
        analysis_cycle,
        max_cycles,
    )

    return GovernanceState(
        requirement_class=requirement_class,
        gov_class=gov_class,
        rfq_admissible=rfq_admissible,
        validity_limits=validity_limits,
        open_validation_points=open_validation_points,
        preselection_blockers=readiness.preselection_blockers,
        missing_but_assumable=readiness.missing_but_assumable,
        optional_context=readiness.optional_context,
        compliance_blockers=readiness.compliance_blockers,
        type_sensitive_required=readiness.type_sensitive_required,
    )


def determine_changed_parameter_fields(
    previous: NormalizedState,
    current: NormalizedState,
) -> set[str]:
    """Return canonical upstream fields whose normalized value changed."""

    changed_fields: set[str] = set()
    all_fields = set(previous.parameters) | set(current.parameters)

    for field_name in all_fields:
        before = previous.parameters.get(field_name)
        after = current.parameters.get(field_name)

        if before is None or after is None:
            changed_fields.add(field_name)
            continue

        if (
            before.value != after.value
            or before.unit != after.unit
            or before.source != after.source
        ):
            changed_fields.add(field_name)

        if field_name == "medium" and before.confidence != after.confidence:
            changed_fields.add("medium_confidence")

    return changed_fields


def invalidate_downstream(
    changed_field: str,
    state: GovernedSessionState,
) -> GovernedSessionState:
    """Mark dependent downstream artefacts as stale for one changed upstream field."""

    affected = DEPENDENCY_MAP.get(changed_field, [])
    if not affected:
        return state

    derived_status = dict(state.derived.field_status)
    decision_status = dict(state.decision.field_status)

    for field_name in affected:
        if field_name == "preselection":
            decision_status["preselection"] = "stale"
            continue

        if field_name == "requirement_class":
            derived_status["requirement_class"] = "stale"
            decision_status["requirement_class"] = "stale"
            continue

        derived_status[field_name] = "stale"

    derived = state.derived.model_copy(update={"field_status": derived_status})
    decision = state.decision.model_copy(
        update={
            "preselection": None,
            "field_status": decision_status,
        }
    )
    action_readiness = state.action_readiness.model_copy(
        update={
            "pdf_ready": False,
            "pdf_url": None,
        }
    )

    return state.model_copy(
        update={
            "derived": derived,
            "decision": decision,
            "action_readiness": action_readiness,
        }
    )


# ---------------------------------------------------------------------------
# S3 — single-writer governed-layer content syncs (P1-4 PR5b)
#
# Per the architecture rule at the top of this module, GovernanceState /
# DecisionState instances may only be PRODUCED by reducers. These two helpers are
# the sanctioned out-of-chain producers: deterministic content syncs (no LLM, no
# I/O) that call sites use instead of a raw
# `state.governance.model_copy(...)` / `state.decision.model_copy(...)`, so the
# single-writer invariant holds literally (incl. model_copy), not just for direct
# constructors. Enforced by tests/architecture/test_single_writer_invariant.py.
# ---------------------------------------------------------------------------


def produce_governance(governance: GovernanceState, **updates: Any) -> GovernanceState:
    """Deterministic content-sync producing a new GovernanceState (single-writer)."""
    return governance.model_copy(update=updates)


def produce_decision(decision: DecisionState, **updates: Any) -> DecisionState:
    """Deterministic content-sync producing a new DecisionState (single-writer)."""
    return decision.model_copy(update=updates)
