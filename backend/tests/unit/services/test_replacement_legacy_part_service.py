from __future__ import annotations

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType
from app.services.replacement_legacy_part_service import (
    ReplacementLegacyPartService,
    build_replacement_legacy_part_intake,
)


def test_dimension_only_old_part_becomes_uncertain_legacy_intake() -> None:
    bundle = ReplacementLegacyPartService().build("Auf dem Teil steht nur 75x95x10.")

    assert bundle.primary_case_type == CaseType.unknown_legacy_part.value
    assert (
        bundle.legacy_part_intake.artifact_type == ArtifactType.legacy_part_intake.value
    )
    assert bundle.legacy_part_intake.part_candidate.dimensions == {
        "shaft_diameter_mm": 75.0,
        "housing_bore_mm": 95.0,
        "width_mm": 10.0,
    }
    assert bundle.legacy_part_intake.identity_confidence.level == "low"
    assert "Foto der Beschriftung" in bundle.legacy_part_intake.required_evidence
    assert "Messmethode und Toleranzen der Masse" in (
        bundle.legacy_part_intake.required_evidence
    )


def test_article_material_and_evidence_raise_confidence_only_to_medium() -> None:
    bundle = build_replacement_legacy_part_intake(
        {
            "case_type": "replacement_reorder",
            "article_number": "ERP-12345",
            "text": "Ersatzteil 75x95x10 FKM wird wieder benoetigt.",
            "photos": ["front.jpg", "back.jpg"],
        }
    )

    assert bundle.primary_case_type == CaseType.replacement_reorder.value
    assert bundle.replacement_sheet.part_candidate.article_number == "ERP-12345"
    assert bundle.replacement_sheet.part_candidate.material_hint == "FKM"
    assert bundle.replacement_sheet.identity_confidence.level == "medium"
    assert bundle.replacement_sheet.identity_confidence.score < 1.0


def test_required_photos_measures_and_context_are_listed() -> None:
    bundle = ReplacementLegacyPartService().build("Wir brauchen dasselbe Teil wieder.")

    required = bundle.replacement_sheet.required_evidence

    assert "Foto der Beschriftung" in required
    assert "Foto von Vorder- und Rueckseite" in required
    assert "Masse: Welle, Gehaeuse, Breite" in required
    assert "Anwendungskontext und Medium" in required


def test_replacement_artifacts_do_not_claim_interchangeability() -> None:
    bundle = ReplacementLegacyPartService().build("Auf dem Teil steht nur 75x95x10.")
    rendered = str(bundle.as_dict()).casefold()

    forbidden = (
        "1:1",
        "sicher ersetzt",
        "sicher austauschbar",
        "austauschbarkeit bestaetigt",
        "freigegeben",
        "zugelassen",
        "geeignet",
    )
    assert all(term not in rendered for term in forbidden)
    assert "zu bestaetigen" in rendered


def test_replacement_bundle_serializes_projection() -> None:
    payload = ReplacementLegacyPartService().build("Ersatzteil 75x95x10.").as_dict()

    assert payload["schema_version"] == "replacement_legacy_part_v0.8.3"
    assert payload["artifact_types"] == (
        "replacement_sheet",
        "legacy_part_intake",
    )
    assert payload["event_names"] == (
        "ReplacementLegacyContextCollected",
        "LegacyPartCandidateExtracted",
        "IdentityConfidenceComputed",
        "ReplacementSheetGenerated",
        "LegacyPartIntakeGenerated",
    )
