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
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    AssumptionRef,
    ConflictRef,
    ConfidenceLevel,
    DecisionState,
    DerivedState,
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
    "rpm": ["pv_value", "velocity", "material_suitability"],
    "shaft_diameter": ["pv_value", "velocity"],
    "shaft_diameter_mm": ["pv_value", "velocity"],
    "pressure": ["requirement_class", "material_suitability"],
    "pressure_bar": ["requirement_class", "material_suitability"],
    "medium_confidence": ["material_suitability"],
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
        return c if c in ("confirmed", "estimated", "inferred", "requires_confirmation") else "requires_confirmation"
    try:
        return _float_to_confidence(float(c))
    except (TypeError, ValueError):
        return "requires_confirmation"


# ---------------------------------------------------------------------------
# Core required fields for governance
# ---------------------------------------------------------------------------

# Minimum set of fields that must be asserted at CONFIRMED or ESTIMATED
# confidence before Class A governance is reachable.
_CORE_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "medium",
    "pressure_bar",
    "temperature_c",
})

# Fields at INFERRED or REQUIRES_CONFIRMATION confidence → blocking_unknowns
_BLOCKING_CONFIDENCE_LEVELS: frozenset[ConfidenceLevel] = frozenset({
    "requires_confirmation",
})

# Fields at these confidence levels may be asserted (with caveats)
_ASSERTABLE_CONFIDENCE_LEVELS: frozenset[ConfidenceLevel] = frozenset({
    "confirmed",
    "estimated",
    "inferred",
})


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
            parameters[field_name] = NormalizedParameter(
                field_name=field_name,
                value=ov.override_value,
                unit=ov.override_unit,
                confidence="confirmed",
                source="user_override",
                source_turn=ov.turn_index,
            )
            parameter_status[field_name] = "observed"
            log.debug("[reducer] field=%s source=user_override value=%r", field_name, ov.override_value)
            continue

        exts = extractions_by_field.get(field_name, [])
        if not exts:
            continue

        # Sort by confidence (desc) then turn_index (desc — more recent wins ties)
        _CONF_RANK = {"confirmed": 4, "estimated": 3, "inferred": 2, "requires_confirmation": 1}
        exts_sorted = sorted(
            exts,
            key=lambda e: (_CONF_RANK.get(_extraction_confidence(e), 0), e.turn_index),
            reverse=True,
        )
        best = exts_sorted[0]

        # Conflict detection: different raw_value strings from LLM extractions
        unique_values = {_canonical_value(e.raw_value) for e in exts}
        if len(unique_values) > 1:
            conflicts.append(ConflictRef(
                field_name=field_name,
                description=(
                    f"Conflicting extractions for '{field_name}': "
                    + ", ".join(repr(v) for v in sorted(str(v) for v in unique_values))
                ),
                severity="warning",
            ))
            log.debug("[reducer] conflict detected for field=%s values=%s", field_name, unique_values)

        # Confidence grade of the best extraction
        confidence: ConfidenceLevel = _extraction_confidence(best)

        if confidence == "requires_confirmation":
            assumptions.append(AssumptionRef(
                field_name=field_name,
                description=f"'{field_name}' requires user confirmation (value: {best.raw_value!r})",
            ))
            parameter_status[field_name] = "assumed"
        else:
            parameter_status[field_name] = "observed"

        parameters[field_name] = NormalizedParameter(
            field_name=field_name,
            value=best.raw_value,
            unit=best.raw_unit,
            confidence=confidence,
            source="llm",
            source_turn=best.turn_index,
        )

    return NormalizedState(
        parameters=parameters,
        unit_system="SI",
        conflicts=conflicts,
        assumptions=assumptions,
        parameter_status=parameter_status,
    )


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
    1. Parameters at 'confirmed' or 'estimated' confidence → AssertedClaim.
    2. Parameters at 'inferred' confidence → AssertedClaim (with caveat note).
    3. Parameters at 'requires_confirmation' → blocking_unknowns.
    4. Blocking ConflictRefs → conflict_flags.
    5. Evidence claims can upgrade an 'inferred' parameter to 'confirmed'
       if the claim field_name matches and claim.confidence == 'confirmed'.
    6. Core required fields that are absent entirely → blocking_unknowns.

    Returns a new AssertedState. Never mutates inputs.
    """
    evidence = evidence or []

    # Build evidence index: field_name → best claim
    evidence_index: dict[str, Claim] = {}
    _CONF_RANK = {"confirmed": 4, "estimated": 3, "inferred": 2, "requires_confirmation": 1}
    for claim in evidence:
        existing = evidence_index.get(claim.field_name)
        if existing is None or _CONF_RANK.get(claim.confidence, 0) > _CONF_RANK.get(existing.confidence, 0):
            evidence_index[claim.field_name] = claim

    assertions: dict[str, AssertedClaim] = {}
    blocking_unknowns: list[str] = []
    conflict_flags: list[str] = []

    # ── Process normalized parameters ────────────────────────────────────
    for field_name, param in normalized.parameters.items():
        confidence = param.confidence

        # Evidence upgrade: inferred → confirmed if evidence says so
        if confidence == "inferred" and field_name in evidence_index:
            ev = evidence_index[field_name]
            if ev.confidence in ("confirmed", "estimated"):
                confidence = ev.confidence
                log.debug(
                    "[reducer] evidence upgrade field=%s inferred→%s (claim=%s)",
                    field_name,
                    confidence,
                    ev.claim_id,
                )

        if confidence == "requires_confirmation":
            blocking_unknowns.append(field_name)
        elif confidence in ("confirmed", "estimated", "inferred"):
            ev_refs = [evidence_index[field_name].claim_id] if field_name in evidence_index else []
            assertions[field_name] = AssertedClaim(
                field_name=field_name,
                asserted_value=param.value,
                evidence_refs=ev_refs,
                confidence=confidence,
            )

    # ── Conflict flags from blocking conflicts ───────────────────────────
    for conflict in normalized.conflicts:
        if conflict.severity == "blocking" and conflict.field_name not in conflict_flags:
            conflict_flags.append(conflict.field_name)

    # ── Core fields missing entirely → blocking unknowns ─────────────────
    for core_field in _CORE_REQUIRED_FIELDS:
        if core_field not in assertions and core_field not in blocking_unknowns:
            blocking_unknowns.append(core_field)

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
        f for f in _CORE_REQUIRED_FIELDS
        if f in asserted.assertions
        and asserted.assertions[f].confidence in ("confirmed", "estimated")
    }
    has_blocking_unknowns = bool(asserted.blocking_unknowns)
    has_conflict_flags = bool(asserted.conflict_flags)
    cycle_exceeded = analysis_cycle >= max_cycles

    # ── Determine governance class ────────────────────────────────────────
    gov_class: GovClass

    if not core_asserted:
        # No core fields at all → out of scope
        gov_class = "D"
    elif cycle_exceeded and has_blocking_unknowns:
        # Cycle limit exceeded with unresolved unknowns → force Class C
        gov_class = "C"
    elif has_conflict_flags:
        # Unresolvable conflicts → Class C
        gov_class = "C"
    elif not has_blocking_unknowns and core_asserted >= _CORE_REQUIRED_FIELDS:
        # All core fields asserted, no blockers → Class A
        gov_class = "A"
    else:
        # Partial assertions, some unknowns, within cycle limit → Class B
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
    open_validation_points: list[str] = list(asserted.blocking_unknowns)
    if has_conflict_flags:
        open_validation_points += [
            f"Unresolved conflict: '{f}'" for f in asserted.conflict_flags
        ]

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
