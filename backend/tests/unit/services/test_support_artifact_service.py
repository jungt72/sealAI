from __future__ import annotations

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType
from app.services.support_artifact_service import (
    SupportArtifactService,
    build_support_artifacts,
)


def test_customer_reply_draft_is_helpful_but_not_decisive() -> None:
    bundle = SupportArtifactService().build(
        {
            "case_type": "manufacturer_support_intake",
            "case_summary": "Kunde fragt WDR AS 75x95x10 FKM mit Oelbericht an.",
            "missing_values": ["Druck", "Temperatur", "Kontaktzeit"],
        }
    )

    draft = bundle.customer_reply_draft

    assert bundle.case_type == CaseType.manufacturer_support_intake.value
    assert draft.artifact_type == ArtifactType.customer_reply_draft.value
    assert "Druck" in draft.requested_information
    assert "Temperatur" in draft.requested_information
    assert any("technische Klaerung" in line for line in draft.body_lines)
    assert any("Herstellerdaten" in line for line in draft.body_lines)


def test_internal_engineering_note_contains_evidence_and_open_points() -> None:
    bundle = build_support_artifacts(
        {
            "case_summary": "Supportfall mit FKM-Dichtung und Medienbericht.",
            "open_points": [
                {
                    "field": "Compoundbezeichnung",
                    "reason": "Materialfamilie reicht nicht aus.",
                    "priority": "high",
                },
                "Laborverfahren",
            ],
            "evidence_refs": [
                {
                    "label": "Oelbericht.pdf",
                    "source_type": "uploaded_evidence",
                    "validation_status": "candidate",
                    "reference": "doc-1",
                }
            ],
        }
    )

    note = bundle.internal_engineering_note

    assert note.artifact_type == ArtifactType.internal_engineering_note.value
    assert note.evidence_refs[0].label == "Oelbericht.pdf"
    assert note.evidence_refs[0].validation_status == "candidate"
    assert {point.field for point in note.open_points} == {
        "Compoundbezeichnung",
        "Laborverfahren",
    }
    assert any("Material" in action for action in note.review_actions)


def test_support_artifacts_contain_no_liability_or_final_claim() -> None:
    bundle = SupportArtifactService().build(
        "Der Kunde meldet Leckage nach kurzer Laufzeit und fragt nach Ersatz."
    )
    rendered = " ".join(
        (
            *bundle.customer_reply_draft.body_lines,
            bundle.customer_reply_draft.boundary_notice,
            *bundle.internal_engineering_note.technical_notes,
            *bundle.internal_engineering_note.review_actions,
            *bundle.internal_engineering_note.claim_guard,
        )
    ).casefold()

    forbidden = (
        "haftung",
        "schuld",
        "wir erkennen an",
        "verursacht durch uns",
        "root cause confirmed",
        "ursache bestaetigt",
        "freigegeben",
        "zugelassen",
        "geeignet",
        "compliant",
    )
    assert all(term not in rendered for term in forbidden)


def test_support_artifact_bundle_serializes_safely() -> None:
    payload = (
        SupportArtifactService()
        .build(
            {
                "case_summary": "Technische Rueckfrage zu Pumpendichtung.",
                "missing_required_fields": ["Pumpentyp"],
            }
        )
        .as_dict()
    )

    assert payload["schema_version"] == "support_artifacts_v0.8.3"
    assert payload["artifact_types"] == (
        "customer_reply_draft",
        "internal_engineering_note",
    )
    assert payload["customer_reply_draft"]["requested_information"] == ("Pumpentyp",)
    assert payload["event_names"] == (
        "SupportArtifactContextCollected",
        "CustomerReplyDraftGenerated",
        "InternalEngineeringNoteGenerated",
    )
