from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.services.capability_service import (
    ManufacturerCapabilityProfile,
    PartnerCapabilityProjection,
)
from app.services.problem_first_matching_service import (
    ManufacturerMatch,
    ProblemFirstMatchingService,
)


PARTNER_NETWORK_DISCLOSURE = (
    "SeaLAI zeigt hier nur Partnerprofile, die im Netzwerk hinterlegt sind. "
    "Bezahlung darf die fachliche Einordnung nicht verbessern. "
    "Der Hersteller muss die Auslegung prüfen."
)


@dataclass(frozen=True, slots=True)
class ManufacturerFitRow:
    manufacturer_id: str
    fit_score: float
    verification_level: str
    fit_reasons: tuple[str, ...]
    gaps: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    source_claim_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManufacturerFitMatrix:
    status: str
    disclosure: str
    rows: tuple[ManufacturerFitRow, ...]
    no_suitable_partner_reason: str | None = None
    eligible_partner_count: int = 0


class ManufacturerFitMatrixService:
    """Compute a transparent technical fit matrix inside the paid partner layer."""

    def __init__(self, matcher: ProblemFirstMatchingService | None = None) -> None:
        self._matcher = matcher or ProblemFirstMatchingService()

    def compute(
        self,
        case: Mapping[str, Any],
        partner_projections: Sequence[PartnerCapabilityProjection],
    ) -> ManufacturerFitMatrix:
        eligible = [projection for projection in partner_projections if projection.active_paid]
        profiles = [projection.capability_profile for projection in eligible]
        matches = self._matcher.match_manufacturer_profiles(case, profiles)
        projection_by_id = {projection.manufacturer_id: projection for projection in eligible}
        match_by_id = {match.manufacturer_id: match for match in matches}

        rows: list[ManufacturerFitRow] = []
        for match in matches:
            projection = projection_by_id.get(match.manufacturer_id)
            if projection is None:
                continue
            rows.append(_fit_row(case, projection, match))

        if not rows:
            return ManufacturerFitMatrix(
                status="no_suitable_partner",
                disclosure=PARTNER_NETWORK_DISCLOSURE,
                rows=(),
                no_suitable_partner_reason=_no_fit_reason(case, eligible),
                eligible_partner_count=len(eligible),
            )

        return ManufacturerFitMatrix(
            status="fit_computed",
            disclosure=PARTNER_NETWORK_DISCLOSURE,
            rows=tuple(rows),
            eligible_partner_count=len(eligible),
        )


def _fit_row(
    case: Mapping[str, Any],
    projection: PartnerCapabilityProjection,
    match: ManufacturerMatch,
) -> ManufacturerFitRow:
    gaps = _profile_gaps(case, projection.capability_profile)
    return ManufacturerFitRow(
        manufacturer_id=projection.manufacturer_id,
        fit_score=match.total_score,
        verification_level=projection.verification_level,
        fit_reasons=_fit_reasons(case, projection.capability_profile, projection.verification_level),
        gaps=tuple(gaps),
        missing_requirements=match.capability_coverage.unmet,
        source_claim_ids=projection.source_claim_ids,
    )


def _fit_reasons(
    case: Mapping[str, Any],
    profile: ManufacturerCapabilityProfile,
    verification_level: str,
) -> tuple[str, ...]:
    reasons: list[str] = []
    engineering_path = _text(case.get("engineering_path"))
    material = _text(case.get("sealing_material_family"))
    quantity = _quantity(case.get("quantity_requested"))
    if engineering_path and engineering_path in profile.supported_seal_types:
        reasons.append(f"seal_type:{engineering_path}")
    if material and material in profile.supported_material_families:
        reasons.append(f"material_family:{material}")
    if quantity is not None and (quantity > 10 or profile.small_quantity_capable is True):
        reasons.append("quantity_window:covered")
    if case.get("atex_required") and profile.atex_capable is True:
        reasons.append("atex_capability:covered")
    reasons.append(f"verification_level:{verification_level}")
    return tuple(reasons)


def _profile_gaps(
    case: Mapping[str, Any],
    profile: ManufacturerCapabilityProfile,
) -> list[str]:
    gaps: list[str] = []
    engineering_path = _text(case.get("engineering_path"))
    material = _text(case.get("sealing_material_family"))
    quantity = _quantity(case.get("quantity_requested"))
    if engineering_path and engineering_path not in profile.supported_seal_types:
        gaps.append("engineering_path")
    if material and material not in profile.supported_material_families:
        gaps.append("material_expertise")
    if quantity is not None and quantity <= 10 and profile.small_quantity_capable is not True:
        gaps.append("lot_size_capability")
    if case.get("atex_required") and profile.atex_capable is not True:
        gaps.append("certification")
    return gaps


def _no_fit_reason(
    case: Mapping[str, Any],
    projections: Sequence[PartnerCapabilityProjection],
) -> str:
    if not projections:
        return "no_active_paid_partner"
    gap_counts: dict[str, int] = {}
    for projection in projections:
        for gap in _profile_gaps(case, projection.capability_profile):
            gap_counts[gap] = gap_counts.get(gap, 0) + 1
    if not gap_counts:
        return "eligible_partner_capabilities_insufficient"
    return "missing:" + ",".join(sorted(gap_counts))


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _quantity(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        raw = raw.get("pieces")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
