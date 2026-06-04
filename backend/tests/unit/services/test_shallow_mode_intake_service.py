from __future__ import annotations

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType
from app.services.shallow_mode_intake_service import (
    ShallowModeIntakeService,
    build_shallow_mode_intake,
)


def test_drawing_upload_becomes_drawing_review_candidate() -> None:
    bundle = ShallowModeIntakeService().build(
        {"documents": [{"label": "zeichnung-rev-a.pdf"}]}
    )

    assert bundle.primary_case_type == CaseType.drawing_review.value
    assert bundle.artifact_type == ArtifactType.drawing_review.value
    assert bundle.artifact.evidence_refs == ("zeichnung-rev-a.pdf",)
    assert bundle.artifact.status == "candidate_review"
    assert "Zeichnungsrevision" in bundle.artifact.open_points


def test_quote_comparison_does_not_recommend_cheapest_option() -> None:
    bundle = build_shallow_mode_intake(
        "Welche von drei Angeboten passt technisch am besten?"
    )
    rendered = str(bundle.as_dict()).casefold()

    assert bundle.primary_case_type == CaseType.quote_comparison.value
    assert bundle.artifact_type == ArtifactType.quote_comparison.value
    assert "preis allein bestimmt keine technische richtung" in rendered
    forbidden = ("billigste", "guenstigste", "nimm angebot", "bestes angebot")
    assert all(term not in rendered for term in forbidden)


def test_pfas_fkm_replacement_creates_substitution_risk_brief() -> None:
    bundle = ShallowModeIntakeService().build(
        "PFAS-freie Alternative zu FKM gesucht."
    )

    assert bundle.primary_case_type == CaseType.material_substitution.value
    assert bundle.artifact_type == ArtifactType.material_substitution_brief.value
    assert bundle.artifact.status == "risk_brief_candidate"
    assert "Ausgangswerkstoff" in bundle.artifact.open_points
    assert "Hersteller- oder Compoundpruefung" in bundle.artifact.boundary_notice


def test_emergency_triage_asks_exactly_one_most_important_question() -> None:
    bundle = ShallowModeIntakeService().build("Anlage steht, wir brauchen heute Ersatz.")

    assert bundle.primary_case_type == CaseType.emergency_mro.value
    assert bundle.artifact_type == ArtifactType.emergency_triage.value
    assert bundle.artifact.status == "urgent_triage"
    assert bundle.artifact.next_question.count("?") == 1
    assert "keine Bestellung" in bundle.artifact.boundary_notice


def test_shallow_artifact_has_no_final_claims() -> None:
    bundle = ShallowModeIntakeService().build("Kann diese Zeichnung gefertigt werden?")
    rendered = str(bundle.as_dict()).casefold()

    forbidden = (
        "freigegeben",
        "sicher herstellbar",
        "gleichwertig",
        "pauschale alternative",
        "dispatch",
    )
    assert all(term not in rendered for term in forbidden)


def test_shallow_bundle_serializes_projection() -> None:
    payload = ShallowModeIntakeService().build("Anlage steht.").as_dict()

    assert payload["schema_version"] == "shallow_mode_intake_v0.8.3"
    assert payload["event_names"] == (
        "ShallowModeIntentIdentified",
        "CaseTypeAssigned",
        "ShallowIntakeGenerated",
    )
