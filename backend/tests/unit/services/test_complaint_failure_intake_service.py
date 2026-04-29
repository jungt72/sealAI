from __future__ import annotations

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType
from app.services.complaint_failure_intake_service import (
    ComplaintFailureIntakeService,
    build_complaint_failure_intake,
)


def test_failed_after_three_months_creates_failure_intake() -> None:
    bundle = ComplaintFailureIntakeService().build(
        "Dichtung nach 3 Monaten ausgefallen, Salzwasser, 80 Grad."
    )

    assert bundle.primary_case_type == CaseType.failure_analysis.value
    assert bundle.failure_analysis_intake.artifact_type == (
        ArtifactType.failure_analysis_intake.value
    )
    assert any(
        pattern.pattern == "premature_failure"
        for pattern in bundle.failure_analysis_intake.damage_patterns
    )
    assert any(
        candidate.field == "operating_duration"
        and candidate.raw_value == "3 Monaten"
        for candidate in bundle.failure_analysis_intake.operating_conditions
    )
    assert "damage_evidence" in bundle.failure_analysis_intake.open_points


def test_leaks_again_creates_complaint_triage_with_evidence_request() -> None:
    bundle = build_complaint_failure_intake(
        "Der Kunde sagt: die Dichtung leckt wieder am Getriebeausgang."
    )

    assert bundle.primary_case_type == CaseType.complaint_case.value
    assert bundle.complaint_intake.artifact_type == ArtifactType.complaint_intake.value
    assert any(
        pattern.pattern == "leakage"
        for pattern in bundle.complaint_intake.damage_patterns
    )
    assert "Foto der Dichtlippe / Laufspur" in bundle.complaint_intake.requested_evidence
    assert "operating_conditions" in bundle.complaint_intake.open_points


def test_evidence_refs_suppress_photo_request_but_keep_candidates() -> None:
    bundle = ComplaintFailureIntakeService().build(
        {
            "case_type": "failure_analysis",
            "damage_description": "Dichtung verschlissen bei 6 bar und 1200 rpm.",
            "evidence_refs": [{"label": "foto-1.jpg"}],
        }
    )

    assert bundle.primary_case_type == CaseType.failure_analysis.value
    assert bundle.failure_analysis_intake.requested_evidence == ()
    assert any(
        condition.field == "pressure" and condition.raw_value == "6 bar"
        for condition in bundle.failure_analysis_intake.operating_conditions
    )
    assert all(
        pattern.status == "candidate"
        for pattern in bundle.failure_analysis_intake.damage_patterns
    )


def test_intake_contains_no_confirmed_cause_or_liability_statement() -> None:
    bundle = ComplaintFailureIntakeService().build(
        "Kundenreklamation: Dichtung leckt wieder nach 3 Monate."
    )
    rendered = str(bundle.as_dict()).casefold()

    forbidden = (
        "rootcauseconfirmed",
        "ursache bestaetigt",
        "ursache ist",
        "schuld",
        "haftung",
        "wir erkennen an",
        "verursacht durch uns",
    )
    assert all(term not in rendered for term in forbidden)
    assert "failureanalysisintakegenerated" in rendered


def test_bundle_serializes_intake_projection() -> None:
    payload = ComplaintFailureIntakeService().build(
        "Dichtung ausgefallen."
    ).as_dict()

    assert payload["schema_version"] == "complaint_failure_intake_v0.8.3"
    assert payload["artifact_types"] == (
        "complaint_intake",
        "failure_analysis_intake",
    )
    assert payload["event_names"] == (
        "ComplaintFailureContextCollected",
        "DamagePatternCandidateIdentified",
        "OperatingConditionCandidateExtracted",
        "EvidenceRequestGenerated",
        "ComplaintIntakeCreated",
        "FailureAnalysisIntakeGenerated",
    )
