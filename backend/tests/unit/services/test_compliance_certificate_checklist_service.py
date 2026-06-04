from __future__ import annotations

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType
from app.services.compliance_certificate_checklist_service import (
    ComplianceCertificateChecklistService,
    build_compliance_certificate_checklist,
)


def test_fkm_fda_is_requirement_not_application_release() -> None:
    artifact = ComplianceCertificateChecklistService().build("FKM FDA fuer Anlage")

    assert artifact.case_type == CaseType.compliance_certificate_request.value
    assert artifact.artifact_type == ArtifactType.compliance_checklist.value
    assert artifact.material_context.material_family == "FKM"
    assert artifact.material_context.compound_identifier is None
    assert "compound_identifier" in artifact.material_context.open_points
    assert artifact.requirements[0].standard == "FDA"
    assert artifact.requirements[0].evidence_status == "required_missing"
    assert "FDA.evidence" in artifact.open_evidence


def test_certificate_artifact_splits_material_compound_and_documents() -> None:
    artifact = build_compliance_certificate_checklist(
        {
            "text": "PTFE Compound TFM-1700 mit EU 1935/2004 und EU 10/2011",
            "documents": [{"label": "declaration.pdf"}],
        }
    )

    assert artifact.material_context.material_family == "PTFE"
    assert artifact.material_context.compound_identifier == "TFM-1700"
    standards = {requirement.standard for requirement in artifact.requirements}
    assert {"EU 1935/2004", "EU 10/2011"} <= standards
    assert all(
        requirement.evidence_status == "candidate_evidence_present"
        for requirement in artifact.requirements
    )
    assert all(
        requirement.evidence_refs == ("declaration.pdf",)
        for requirement in artifact.requirements
    )


def test_atex_and_ta_luft_require_scope_specific_evidence() -> None:
    artifact = ComplianceCertificateChecklistService().build(
        "ATEX Zone 1 und TA-Luft Nachweis benoetigt."
    )

    standards = {requirement.standard for requirement in artifact.requirements}
    assert {"ATEX", "TA-Luft"} <= standards
    assert "ATEX.evidence" in artifact.open_evidence
    assert "TA-Luft.evidence" in artifact.open_evidence
    assert any("ATEX-Zone" in item for item in artifact.open_evidence)


def test_compliance_checklist_has_no_approval_claim_without_evidence() -> None:
    artifact = ComplianceCertificateChecklistService().build("FKM FDA")
    rendered = str(artifact.as_dict()).casefold()

    forbidden = (
        "freigegeben",
        "zugelassen",
        "zertifiziert",
        "fda-konform",
        "atex-zertifiziert",
        "compliance approval",
        "approved",
        "passed",
    )
    assert all(term not in rendered for term in forbidden)
    assert "required_missing" in rendered


def test_compliance_checklist_serializes_projection() -> None:
    payload = (
        ComplianceCertificateChecklistService()
        .build("Brauche USP Class VI fuer EPDM.")
        .as_dict()
    )

    assert payload["schema_version"] == "compliance_checklist_v0.8.3"
    assert payload["artifact_type"] == "compliance_checklist"
    assert payload["requirements"][0]["standard"] == "USP Class VI"
    assert payload["event_names"] == (
        "ComplianceCertificateRequestIdentified",
        "ComplianceRequirementCaptured",
        "ComplianceEvidenceMarkedOpen",
        "ComplianceChecklistGenerated",
    )
