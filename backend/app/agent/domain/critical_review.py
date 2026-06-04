from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CriticalReviewGovernanceSummary:
    release_status: str = "inadmissible"
    rfq_admissibility: str = "inadmissible"
    unknowns_release_blocking: tuple[str, ...] = ()
    unknowns_manufacturer_validation: tuple[str, ...] = ()
    scope_of_validity: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    review_required: bool = False


@dataclass(frozen=True)
class CriticalReviewRecommendationPackage:
    requirement_class: dict[str, Any] | None = None


@dataclass(frozen=True)
class CriticalReviewMatchingPackage:
    status: str = ""
    selected_manufacturer_ref: dict[str, Any] | None = None


@dataclass(frozen=True)
class CriticalReviewRfqBasis:
    rfq_object: dict[str, Any] | None = None
    recipient_refs: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class CriticalReviewSpecialistInput:
    governance_summary: CriticalReviewGovernanceSummary
    recommendation_package: CriticalReviewRecommendationPackage
    matching_package: CriticalReviewMatchingPackage
    rfq_basis: CriticalReviewRfqBasis


@dataclass(frozen=True)
class CriticalReviewSpecialistResult:
    critical_review_status: str
    critical_review_passed: bool
    blocking_findings: tuple[str, ...]
    soft_findings: tuple[str, ...]
    required_corrections: tuple[str, ...]


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _compact_dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {str(key): item for key, item in dict(value).items()}


def _compact_refs(values: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    for ref in list(values or []):
        compact = _compact_dict(ref)
        if compact:
            refs.append(compact)
    return tuple(refs)


def critical_review_result_to_dict(
    result: CriticalReviewSpecialistResult,
) -> dict[str, Any]:
    payload = asdict(result)
    payload["blocking_findings"] = list(result.blocking_findings)
    payload["soft_findings"] = list(result.soft_findings)
    payload["required_corrections"] = list(result.required_corrections)
    return payload


def run_critical_review_specialist(
    payload: CriticalReviewSpecialistInput,
) -> CriticalReviewSpecialistResult:
    governance = payload.governance_summary
    recommendation = payload.recommendation_package
    matching = payload.matching_package
    rfq_basis = payload.rfq_basis

    blocking_findings: list[str] = []
    soft_findings: list[str] = []
    required_corrections: list[str] = []

    if governance.release_status != "inquiry_ready":
        _append_unique(blocking_findings, "release_status_not_inquiry_ready")
        _append_unique(required_corrections, "Release status must reach inquiry_ready before RFQ handover.")
    if governance.rfq_admissibility != "ready":
        _append_unique(blocking_findings, "rfq_admissibility_not_ready")
        _append_unique(required_corrections, "RFQ admissibility must be ready before RFQ handover.")

    if governance.unknowns_release_blocking:
        _append_unique(blocking_findings, "unknowns_release_blocking")
        _append_unique(required_corrections, "Resolve release-blocking unknowns before RFQ handover.")

    if governance.conflicts:
        _append_unique(blocking_findings, "conflicts_present")
        _append_unique(required_corrections, "Resolve conflicting governed inputs before RFQ handover.")

    if governance.review_required:
        _append_unique(blocking_findings, "review_pending")
        _append_unique(required_corrections, "Resolve the pending review before RFQ handover.")

    requirement_class = _compact_dict(recommendation.requirement_class)
    requirement_class_id = str(
        requirement_class.get("requirement_class_id")
        or requirement_class.get("class_id")
        or ""
    ).strip()
    if not requirement_class_id:
        _append_unique(blocking_findings, "requirement_class_missing")
        _append_unique(required_corrections, "Resolve the requirement class before RFQ handover.")

    matching_status = str(matching.status or "").strip()
    selected_manufacturer_ref = _compact_dict(matching.selected_manufacturer_ref)
    if matching_status and matching_status != "matched_primary_candidate":
        _append_unique(blocking_findings, "matching_not_releasable")
        _append_unique(required_corrections, "Resolve deterministic matching before RFQ handover.")
    if not selected_manufacturer_ref.get("manufacturer_name"):
        _append_unique(blocking_findings, "selected_manufacturer_missing")
        _append_unique(required_corrections, "Select a deterministic manufacturer candidate before RFQ handover.")

    rfq_object = _compact_dict(rfq_basis.rfq_object)
    recipient_refs = _compact_refs(rfq_basis.recipient_refs)
    if rfq_object and rfq_object.get("requirement_class") is None and requirement_class_id:
        _append_unique(soft_findings, "rfq_object_missing_requirement_class_projection")
    if not recipient_refs:
        _append_unique(soft_findings, "recipient_refs_pending")

    for item in governance.unknowns_manufacturer_validation:
        _append_unique(soft_findings, f"manufacturer_validation:{item}")
    for item in governance.scope_of_validity:
        _append_unique(soft_findings, f"scope:{item}")

    critical_review_passed = not blocking_findings
    return CriticalReviewSpecialistResult(
        critical_review_status="passed" if critical_review_passed else "failed",
        critical_review_passed=critical_review_passed,
        blocking_findings=tuple(blocking_findings),
        soft_findings=tuple(soft_findings),
        required_corrections=tuple(required_corrections),
    )
