"""
Deterministic Inquiry Admissibility Check — Phase H.1.1

check_inquiry_admissibility(state) → AdmissibilityResult

Rules (all deterministic, no LLM):
  1. Mandatory fields must be present in normalized.parameters
  2. parameter_status "assumed" for any critical field → blocking
  3. rfq.blocking_findings from critical_review → blocking

AdmissibilityResult.basis_hash mirrors the decision_basis_hash so that
the inquiry payload is always tied to the exact state snapshot it was
evaluated against.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mandatory fields for an admissible inquiry
# ---------------------------------------------------------------------------

# Canonical parameter names as stored in NormalizedState.parameters
MANDATORY_FIELDS: tuple[str, ...] = (
    "medium",
    "temperature_max_c",
    "pressure_max_bar",
    "shaft_diameter_mm",
    "sealing_type",
)

# Aliases — some nodes write under alternative canonical names
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "temperature_max_c": ("temperature_max_c", "temperature_c", "temp_c"),
    "pressure_max_bar": ("pressure_max_bar", "pressure_bar", "pressure"),
    "shaft_diameter_mm": ("shaft_diameter_mm", "shaft_diameter"),
    "medium": ("medium", "medium_canonical", "medium_classification"),
    "sealing_type": ("sealing_type",),
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdmissibilityResult:
    """Deterministic inquiry admissibility verdict.

    admissible=True  ↔  blocking_reasons is empty
    basis_hash       ties this result to the exact state snapshot evaluated
    """

    admissible: bool
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    basis_hash: str = ""

    def __post_init__(self) -> None:
        # Invariant: admissible=False requires at least one blocking reason
        if not self.admissible and not self.blocking_reasons:
            object.__setattr__(
                self,
                "blocking_reasons",
                ("admissibility_check_failed_no_reason",),
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_normalized_keys(state: Any) -> set[str]:
    """Return the set of field names present in normalized.parameters."""
    try:
        params = state.normalized.parameters
        if isinstance(params, dict):
            return set(params.keys())
    except AttributeError:
        pass
    return set()


def _field_present(state: Any, canonical: str) -> bool:
    """True if any known alias of *canonical* is present in normalized.parameters."""
    present_keys = _get_normalized_keys(state)
    for alias in _FIELD_ALIASES.get(canonical, (canonical,)):
        if alias in present_keys:
            return True
    return False


def _field_status(state: Any, canonical: str) -> Optional[str]:
    """Return the FieldLifecycleStatus for *canonical* (or any alias), or None."""
    try:
        status_map: dict[str, str] = state.normalized.parameter_status or {}
    except AttributeError:
        return None

    for alias in _FIELD_ALIASES.get(canonical, (canonical,)):
        status = status_map.get(alias)
        if status is not None:
            return str(status)

    # Fall back to per-parameter confidence if no parameter_status entry
    try:
        params = state.normalized.parameters or {}
    except AttributeError:
        return None

    for alias in _FIELD_ALIASES.get(canonical, (canonical,)):
        param = params.get(alias)
        if param is None:
            continue
        confidence = getattr(param, "confidence", None) or (
            param.get("confidence") if isinstance(param, dict) else None
        )
        if confidence in ("estimated", "inferred"):
            return "assumed"
    return None


def _blocking_findings_from_rfq(state: Any) -> list[str]:
    """Extract critical_review blocking_findings from rfq state."""
    try:
        findings = state.rfq.blocking_findings
        if isinstance(findings, (list, tuple)):
            return [str(f) for f in findings if f]
    except AttributeError:
        pass
    return []


def _compute_basis_hash(state: Any) -> str:
    """Compact deterministic hash over the normalized+derived snapshot."""
    try:
        from app.agent.state.persistence import compute_decision_basis_hash
        return compute_decision_basis_hash(state)
    except Exception:
        pass

    # Fallback: hash normalized parameters directly
    try:
        params_dump = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
            for k, v in (state.normalized.parameters or {}).items()
        }
        payload = json.dumps(params_dump, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_inquiry_admissibility(state: Any) -> AdmissibilityResult:
    """Deterministic admissibility check — no LLM, no side effects.

    Args:
        state: GovernedSessionState (or any compatible duck-typed object).

    Returns:
        AdmissibilityResult with admissible=True iff all checks pass.
    """
    blocking_reasons: list[str] = []

    # ------------------------------------------------------------------ #
    # Rule 1: mandatory fields must be present
    # ------------------------------------------------------------------ #
    for field_name in MANDATORY_FIELDS:
        if not _field_present(state, field_name):
            blocking_reasons.append(f"missing_mandatory_field:{field_name}")
            log.debug("admissibility: missing mandatory field %r", field_name)

    # ------------------------------------------------------------------ #
    # Rule 2: critical fields must not have status "assumed"
    # ------------------------------------------------------------------ #
    for field_name in MANDATORY_FIELDS:
        status = _field_status(state, field_name)
        if status == "assumed":
            reason = f"assumed_status_for_critical_field:{field_name}"
            if reason not in blocking_reasons:
                blocking_reasons.append(reason)
            log.debug("admissibility: assumed status for critical field %r", field_name)

    # ------------------------------------------------------------------ #
    # Rule 3: critical_review blocking_findings must be empty
    # ------------------------------------------------------------------ #
    findings = _blocking_findings_from_rfq(state)
    for finding in findings:
        reason = f"critical_review_blocking:{finding}"
        if reason not in blocking_reasons:
            blocking_reasons.append(reason)
    if findings:
        log.debug(
            "admissibility: critical_review has %d blocking finding(s): %s",
            len(findings),
            findings,
        )

    # ------------------------------------------------------------------ #
    # Verdict
    # ------------------------------------------------------------------ #
    admissible = not blocking_reasons
    basis_hash = _compute_basis_hash(state)

    return AdmissibilityResult(
        admissible=admissible,
        blocking_reasons=tuple(blocking_reasons),
        basis_hash=basis_hash,
    )


__all__ = [
    "AdmissibilityResult",
    "MANDATORY_FIELDS",
    "check_inquiry_admissibility",
]
