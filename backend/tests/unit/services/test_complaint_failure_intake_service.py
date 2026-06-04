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
        candidate.field == "operating_duration" and candidate.raw_value == "3 Monaten"
        for candidate in bundle.failure_analysis_intake.operating_conditions
    )
    assert "damage_evidence" in bundle.failure_analysis_intake.open_points
    assert (
        bundle.failure_analysis_intake.diagnostic_questions[0].field == "safety_context"
    )
    assert "Ursache" in bundle.failure_analysis_intake.boundary_notice


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
    assert any(
        candidate.field == "leak_location" and candidate.raw_value == "shaft_exit"
        for candidate in bundle.complaint_intake.diagnostic_context
    )
    assert (
        "Fotos im ungewaschenen Originalzustand"
        in bundle.complaint_intake.requested_evidence
    )
    assert (
        "Foto der Dichtlippe / Laufspur" in bundle.complaint_intake.requested_evidence
    )
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


def test_research_grade_failure_intake_extracts_diagnostic_context() -> None:
    bundle = ComplaintFailureIntakeService().build(
        "RWDR leckt am Wellenaustritt nach 20 Stunden. "
        "Medium ist Salzwasser, 6 bar, 80 Grad, 1450 rpm. "
        "Welle 40 mm, Ra 0,4, FKM, Montage war trocken, Riefen an der Gegenlauffläche."
    )
    artifact = bundle.failure_analysis_intake
    context = {
        (candidate.field, candidate.raw_value)
        for candidate in artifact.diagnostic_context
    }
    conditions = {condition.field for condition in artifact.operating_conditions}
    patterns = {pattern.pattern for pattern in artifact.damage_patterns}

    assert ("seal_type", "rwdr") in context
    assert ("leak_location", "shaft_exit") in context
    assert ("medium_at_failure", "Salzwasser") in context
    assert ("shaft_diameter", "40 mm") in context
    assert ("material_or_compound", "FKM") in context
    assert "installation_context" in {field for field, _value in context}
    assert "geometry_surface_context" in {field for field, _value in context}
    assert {"pressure", "temperature", "speed", "operating_duration"}.issubset(
        conditions
    )
    assert "wear" in patterns
    assert "safety_context" in artifact.open_points
    assert artifact.diagnostic_priority[:4] == (
        "safety_context",
        "leak_location",
        "damage_evidence",
        "seal_type",
    )


def test_failure_intake_prioritizes_evidence_before_root_cause_language() -> None:
    bundle = ComplaintFailureIntakeService().build(
        "O-Ring ist aufgequollen und plattgedrückt."
    )
    artifact = bundle.failure_analysis_intake
    questions = [question.field for question in artifact.diagnostic_questions]
    rendered = str(artifact.as_dict()).casefold()

    assert questions[:3] == ["safety_context", "leak_location", "damage_evidence"]
    assert "ursache bleibt offen" in rendered
    assert "ursache ist" not in rendered


def test_bundle_serializes_intake_projection() -> None:
    payload = ComplaintFailureIntakeService().build("Dichtung ausgefallen.").as_dict()

    assert payload["schema_version"] == "complaint_failure_intake_v0.8.3"
    assert payload["artifact_types"] == (
        "complaint_intake",
        "failure_analysis_intake",
    )
    assert payload["event_names"] == (
        "ComplaintFailureContextCollected",
        "DamagePatternCandidateIdentified",
        "OperatingConditionCandidateExtracted",
        "DiagnosticContextCandidateExtracted",
        "EvidenceRequestGenerated",
        "DiagnosticQuestionGenerated",
        "ComplaintIntakeCreated",
        "FailureAnalysisIntakeGenerated",
    )
