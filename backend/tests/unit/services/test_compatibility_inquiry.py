from __future__ import annotations

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType
from app.services.compatibility_inquiry_service import (
    CompatibilityInquiryService,
    build_compatibility_inquiry_artifact,
)


def test_wdr_fkm_fda_designation_is_extracted_as_compatibility_inquiry() -> None:
    artifact = CompatibilityInquiryService().build(
        "Bitte pruefen: WDR AS 75x95x10 DIN 3760 FKM FDA mit Oelbericht."
    )

    assert artifact.case_type == CaseType.compatibility_inquiry.value
    assert artifact.artifact_types == (
        ArtifactType.technical_inquiry_summary.value,
        ArtifactType.compatibility_matrix.value,
    )
    assert artifact.product_designation.seal_type == "radial_shaft_seal"
    assert artifact.product_designation.dimensions == {
        "shaft_diameter_mm": 75.0,
        "housing_bore_mm": 95.0,
        "width_mm": 10.0,
    }
    assert artifact.product_designation.material_family == "FKM"
    assert "DIN 3760" in artifact.product_designation.norm_refs
    assert "FDA" in artifact.product_designation.compliance_flags


def test_water_sodium_and_potassium_are_review_relevant_candidates() -> None:
    artifact = build_compatibility_inquiry_artifact(
        "Wasser, Natrium und Kalium stehen im Bericht, Werte und Einheiten fehlen."
    )

    analytes = {candidate.analyte for candidate in artifact.lab_value_candidates}
    assert {"Wasser", "Natrium", "Kalium"} <= analytes
    assert all(candidate.review_required for candidate in artifact.lab_value_candidates)
    assert any(item.status == "review_required" for item in artifact.compatibility_matrix)


def test_missing_values_units_and_methods_are_open_points() -> None:
    artifact = CompatibilityInquiryService().build(
        "WDR AS 75x95x10 DIN 3760 FKM. Wasser 12, Natrium, Kalium."
    )

    assert "Wasser.unit" in artifact.missing_values
    assert "Wasser.method" in artifact.missing_values
    assert "Natrium.value" in artifact.missing_values
    assert "Natrium.unit" in artifact.missing_values
    assert "Kalium.value" in artifact.missing_values
    assert "Kalium.method" in artifact.missing_values


def test_artifact_contains_no_final_limit_or_compatibility_claim() -> None:
    artifact = CompatibilityInquiryService().build(
        "WDR AS 75x95x10 DIN 3760 FKM FDA. Wasser, Natrium, Kalium."
    )
    rendered = " ".join(
        (
            *artifact.technical_inquiry_summary,
            artifact.boundary_notice,
            *(
                item.reason
                for item in artifact.compatibility_matrix
            ),
        )
    ).casefold()

    forbidden = (
        "geeignet",
        "freigegeben",
        "zugelassen",
        "zertifiziert",
        "konform",
        "compliant",
        "final",
        "sicher passend",
    )
    assert all(term not in rendered for term in forbidden)
    assert "hersteller- oder compoundpruefung erforderlich" in rendered


def test_artifact_serializes_to_safe_projection_dict() -> None:
    payload = CompatibilityInquiryService().build(
        {
            "product_designation": "WDR AS 75x95x10 DIN 3760 FKM",
            "lab_report": "Wasser 12 mg/l Methode ICP",
        }
    ).as_dict()

    assert payload["schema_version"] == "compatibility_inquiry_v0.8.3"
    assert payload["case_type"] == "compatibility_inquiry"
    assert payload["product_designation"]["material_family"] == "FKM"
    assert payload["lab_value_candidates"][0]["status"] == "candidate"
    assert payload["event_names"] == (
        "CompatibilityInquiryClassified",
        "ProductDesignationExtracted",
        "LabValuesMarkedAsCandidates",
        "MissingCompatibilityInputsIdentified",
        "CompatibilityMatrixDerived",
        "TechnicalInquirySummaryDerived",
    )
