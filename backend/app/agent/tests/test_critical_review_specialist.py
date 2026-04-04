from __future__ import annotations

from app.agent.domain.critical_review import (
    CriticalReviewGovernanceSummary,
    CriticalReviewMatchingPackage,
    CriticalReviewRecommendationPackage,
    CriticalReviewRfqBasis,
    CriticalReviewSpecialistInput,
    critical_review_result_to_dict,
    run_critical_review_specialist,
)

_DEFAULT_REQUIREMENT_CLASS = object()


def _payload(
    *,
    release_status: str = "rfq_ready",
    rfq_admissibility: str = "ready",
    review_required: bool = False,
    unknowns_release_blocking: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    requirement_class: dict | object | None = _DEFAULT_REQUIREMENT_CLASS,
    matching_status: str = "matched_primary_candidate",
    selected_manufacturer_name: str | None = "Acme",
    rfq_object: dict | None = None,
    recipient_refs: tuple[dict, ...] = ({"manufacturer_name": "Acme"},),
    scope_of_validity: tuple[str, ...] = (),
    unknowns_manufacturer_validation: tuple[str, ...] = (),
) -> CriticalReviewSpecialistInput:
    return CriticalReviewSpecialistInput(
        governance_summary=CriticalReviewGovernanceSummary(
            release_status=release_status,
            rfq_admissibility=rfq_admissibility,
            unknowns_release_blocking=unknowns_release_blocking,
            unknowns_manufacturer_validation=unknowns_manufacturer_validation,
            scope_of_validity=scope_of_validity,
            conflicts=conflicts,
            review_required=review_required,
        ),
        recommendation_package=CriticalReviewRecommendationPackage(
            requirement_class=(
                {
                    "requirement_class_id": "PTFE10",
                    "description": "PTFE steam sealing class for elevated thermal load.",
                    "seal_type": "gasket",
                }
                if requirement_class is _DEFAULT_REQUIREMENT_CLASS
                else requirement_class
            )
        ),
        matching_package=CriticalReviewMatchingPackage(
            status=matching_status,
            selected_manufacturer_ref=(
                {"manufacturer_name": selected_manufacturer_name}
                if selected_manufacturer_name
                else None
            ),
        ),
        rfq_basis=CriticalReviewRfqBasis(
            rfq_object=rfq_object,
            recipient_refs=recipient_refs,
        ),
    )


def test_valid_package_passes_critical_review() -> None:
    result = run_critical_review_specialist(_payload())

    assert result.critical_review_passed is True
    assert result.blocking_findings == ()
    assert result.required_corrections == ()


def test_blocking_findings_fail_critical_review() -> None:
    result = run_critical_review_specialist(
        _payload(unknowns_release_blocking=("temperature_c",))
    )

    assert result.critical_review_passed is False
    assert "unknowns_release_blocking" in result.blocking_findings
    assert "Resolve release-blocking unknowns before RFQ handover." in result.required_corrections


def test_soft_findings_stay_non_blocking() -> None:
    result = run_critical_review_specialist(
        _payload(
            scope_of_validity=("manufacturer_validation_scope",),
            unknowns_manufacturer_validation=("material",),
        )
    )

    assert result.critical_review_passed is True
    assert "scope:manufacturer_validation_scope" in result.soft_findings
    assert "manufacturer_validation:material" in result.soft_findings


def test_missing_requirement_class_sets_required_correction_without_artificial_safety() -> None:
    result = run_critical_review_specialist(
        _payload(requirement_class=None)
    )

    assert result.critical_review_passed is False
    assert "requirement_class_missing" in result.blocking_findings
    assert "Resolve the requirement class before RFQ handover." in result.required_corrections


def test_result_can_be_projected_back_to_existing_review_dict_shape() -> None:
    result = critical_review_result_to_dict(
        run_critical_review_specialist(
            _payload(rfq_object={"requirement_class": None})
        )
    )

    assert result["critical_review_status"] == "passed"
    assert result["critical_review_passed"] is True
    assert result["soft_findings"] == ["rfq_object_missing_requirement_class_projection"]
