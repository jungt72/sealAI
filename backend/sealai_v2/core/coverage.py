"""Coverage-Gate kernel (V2.2 §4 / INC-COVERAGE-GATE). Deterministic, no LLM, no I/O.

The case-level generalization of the cell-level matrix verdict: given the GROUNDED evidence per axis
— chemical (material x medium, via the gegencheck/matrix kernel), operating-point (the calc envelope
band), archetype (profile coverage) — it emits a deterministic ``coverage_status`` that bounds how
assertive the answer may be (the SS5 status->mode coupling). The LLM consumes the status; it never sets,
overrides, or "feels" it (I-COV-1).

The chemical axis DOMINATES (I-COV-3): chemical/compound suitability is never inferred from first
principles, so an ungrounded chemical axis caps the case at ANALOG_ONLY / OUT_OF_ENVELOPE — never IN.
A grounded ``unvertraeglich`` (disqualified) is GROUNDED evidence — a grounded NO is assertive (SS6.2
"passt nicht (IN)"). ``bedingt`` -> BORDER -> PARTIAL_ENVELOPE (the SS4.3 "PARTIAL baut auf
matrix_conditional auf, kollabiert es nicht").

This module is PURE and, for now, UNWIRED: importing it changes no prod behaviour. Wiring it into the
pipeline (after ``compute``, before ``generate``) and coupling it to the L1 mode is a later, flag-gated
sub-step; the assertivity doctrine goes productive only when the extended eval ruler is green (I-CAL-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CoverageStatus(str, Enum):
    """How far the system's REVIEWED grounding reaches for this case (SS4.2)."""

    IN_ENVELOPE = "in_envelope"  # grounded enough to be assertive — a grounded YES or a grounded NO
    PARTIAL_ENVELOPE = "partial_envelope"  # core grounded, >=1 axis at a grounded edge / `bedingt` -> conditional
    ANALOG_ONLY = "analog_only"  # no direct hit, a near analog exists -> analog + explicit delta + mfr confirm
    OUT_OF_ENVELOPE = "out_of_envelope"  # no grounded hit, no safe analog -> exclusions + test-path + mfr check


class AxisCoverage(str, Enum):
    """Per-evidence-axis grounding state that feeds the case-level status."""

    GROUNDED = "grounded"  # a reviewed hit — compatible OR a grounded disqualification
    BORDER = (
        "border"  # at/near a grounded limit, or a `bedingt` / matrix_conditional cell
    )
    ANALOG = (
        "analog"  # no direct hit, but a near neighbour (same family / adjacent medium)
    )
    MISSING = "missing"  # the axis is relevant to the case but ungrounded
    NOT_APPLICABLE = "not_applicable"  # the case has no such axis (e.g. a pure-geometry decode question)


# cell-level gegencheck `basis` -> case-level chemical-axis coverage
_GEGENCHECK_BASIS = {
    "matrix_compatible": AxisCoverage.GROUNDED,
    "matrix_conditional": AxisCoverage.BORDER,
    "no_matrix_data": AxisCoverage.MISSING,
    "no_medium": AxisCoverage.MISSING,
}


def chemical_axis(gegencheck_verdict: dict | None) -> AxisCoverage:
    """Map the cell-level gegencheck verdict (``core/gegencheck.py``) to chemical-axis coverage.

    ``None`` (no material x medium pairing in the case) -> NOT_APPLICABLE. A grounded disqualification
    (``disqualified=True``) -> GROUNDED (a grounded NO is assertive evidence). ``matrix_conditional`` ->
    BORDER. No reviewed cell / no medium -> MISSING (the analog upgrade is a later sub-step; conservative
    default is MISSING, so the gate never over-claims an analog it cannot ground).
    """
    if gegencheck_verdict is None:
        return AxisCoverage.NOT_APPLICABLE
    if gegencheck_verdict.get("disqualified") is True:
        return AxisCoverage.GROUNDED
    basis = str(gegencheck_verdict.get("basis", ""))
    return _GEGENCHECK_BASIS.get(basis, AxisCoverage.MISSING)


@dataclass(frozen=True)
class CoverageResult:
    status: CoverageStatus
    chemical: AxisCoverage
    operating: AxisCoverage
    archetype: AxisCoverage

    def axis_summary(self) -> str:
        """Deterministic evidence summary — the per-axis hit/miss list (SS4.2), reusable as the SS9
        flywheel gap-signal for PARTIAL/ANALOG/OUT cases."""
        return (
            f"chemical={self.chemical.value} "
            f"operating={self.operating.value} "
            f"archetype={self.archetype.value}"
        )


def classify_coverage(
    *,
    chemical: AxisCoverage,
    operating: AxisCoverage = AxisCoverage.NOT_APPLICABLE,
    archetype: AxisCoverage = AxisCoverage.NOT_APPLICABLE,
) -> CoverageResult:
    """Deterministic case-level coverage from per-axis grounding (SS4.3, refined against the IST-stand).

    Chemical dominates (I-COV-3): an ungrounded chemical axis caps the case at ANALOG_ONLY / OUT — never
    IN. The result bounds the allowed answer mode (SS5); the LLM consumes it, never sets it (I-COV-1).
    """
    return CoverageResult(
        status=_status(chemical, operating, archetype),
        chemical=chemical,
        operating=operating,
        archetype=archetype,
    )


def _status(
    chemical: AxisCoverage, operating: AxisCoverage, archetype: AxisCoverage
) -> CoverageStatus:
    # The chemical (material x medium) axis is the dangerous, dominant one (I-COV-3).
    if chemical is AxisCoverage.MISSING:
        return CoverageStatus.OUT_OF_ENVELOPE
    if chemical is AxisCoverage.ANALOG:
        return CoverageStatus.ANALOG_ONLY
    if chemical is AxisCoverage.BORDER:
        return CoverageStatus.PARTIAL_ENVELOPE
    # chemical is GROUNDED or NOT_APPLICABLE -> the supporting axes decide.
    support = [
        a for a in (operating, archetype) if a is not AxisCoverage.NOT_APPLICABLE
    ]
    if chemical is AxisCoverage.NOT_APPLICABLE and not support:
        return CoverageStatus.OUT_OF_ENVELOPE  # no grounded evidence on any axis
    if any(
        a in (AxisCoverage.BORDER, AxisCoverage.MISSING, AxisCoverage.ANALOG)
        for a in support
    ):
        return CoverageStatus.PARTIAL_ENVELOPE
    return CoverageStatus.IN_ENVELOPE
