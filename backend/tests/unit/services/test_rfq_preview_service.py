from __future__ import annotations

import pytest

from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.services.rfq_preview_service import (
    RFQ_PREVIEW_SECTIONS,
    RfqPreviewError,
    build_rfq_preview_payload,
    collect_open_points,
    collect_technical_fields,
    normalize_consent_scope,
)


def _case() -> CaseRecord:
    return CaseRecord(
        id="case-123",
        case_number="CASE-123",
        user_id="user-1",
        tenant_id="tenant-1",
        case_revision=4,
        request_type="retrofit",
        engineering_path="rwdr",
        sealing_material_family="ptfe_carbon_filled",
        application_pattern_id="agitator",
    )


def _snapshot() -> CaseStateSnapshot:
    return CaseStateSnapshot(
        case_id="case-123",
        revision=4,
        state_json={
            "case_state": {
                "asset_type": "agitator",
                "motion_type": {"value": "rotary"},
                "medium_name": {"canonical_value": "Salzwasser"},
                "temperature_max": {"canonical_value": 80, "unit": "degC"},
                "pressure_nominal": 4,
                "shaft_diameter": 42,
                "missing_required_fields": ["shaft_surface_finish", "speed_rpm"],
                "top_risks": ["corrosion_risk", "unknowns_risk"],
                "manufacturer_review_needs": ["Bitte Federwerkstoff bestaetigen"],
            }
        },
    )


def test_collects_governed_technical_fields_from_case_and_snapshot() -> None:
    fields = collect_technical_fields(case_row=_case(), state=_snapshot().state_json)

    assert fields["application_pattern"] == "agitator"
    assert fields["equipment_type"] == "agitator"
    assert fields["medium_name"] == "Salzwasser"
    assert fields["motion_type"] == "rotary"
    assert fields["pressure_bar"] == 4
    assert fields["shaft_diameter_mm"] == 42
    assert fields["temperature_max_c"] == 80


def test_rfq_preview_payload_is_frozen_and_has_all_v07_sections() -> None:
    payload = build_rfq_preview_payload(case_row=_case(), snapshot=_snapshot())

    assert payload["meta"]["artifact_type"] == "rfq_preview"
    assert payload["meta"]["case_revision"] == 4
    assert payload["meta"]["source_snapshot_revision"] == 4
    assert payload["meta"]["rfq_freeze"] is True
    assert (
        payload["consent_boundary"]["requires_explicit_user_consent_before_sharing"]
        is True
    )
    assert payload["consent_boundary"]["automatic_dispatch_allowed"] is False
    assert [section["title"] for section in payload["rfq_preview"]["sections"]] == list(
        RFQ_PREVIEW_SECTIONS
    )
    assert len(payload["rfq_preview"]["sections"]) == 13
    assert (
        "final technical release"
        in payload["rfq_preview"]["manufacturer_release_boundary"]
    )
    assert payload["decision_understanding"]["case_summary"]
    assert (
        payload["rfq_preview"]["decision_understanding"]
        == payload["decision_understanding"]
    )
    assert any(
        "Salzwasser" in item
        for item in payload["decision_understanding"]["understood_now"]
    )


def test_manufacturer_extract_is_allowlisted_and_revision_bound() -> None:
    payload = build_rfq_preview_payload(case_row=_case(), snapshot=_snapshot())
    extract = payload["manufacturer_extract"]

    assert extract["meta"]["artifact_type"] == "rfq_preview"
    assert extract["meta"]["case_revision"] == 4
    assert extract["technical_parameters"]["medium_name"] == "Salzwasser"
    assert "customer_metadata" not in extract
    assert extract["privacy_boundary"]["mode"] == "allowlist"


def test_open_points_are_deduplicated() -> None:
    state = {
        "a": {"open_points": ["speed", "speed"]},
        "b": {"blocking_unknowns": ["pressure"]},
    }

    assert collect_open_points(state) == ("speed", "pressure")


def test_consent_scope_requires_visible_shared_sections() -> None:
    with pytest.raises(RfqPreviewError):
        normalize_consent_scope({"shared_documents": ["doc-1"]})

    scope = normalize_consent_scope(
        {
            "shared_sections": ["1", "2"],
            "shared_documents": ["doc-1"],
            "intended_recipients": ["manual-export"],
            "user_acknowledged_open_points": True,
            "user_acknowledged_no_final_release": True,
        }
    )
    assert scope["shared_sections"] == ("1", "2")
    assert scope["shared_documents"] == ("doc-1",)
    assert scope["intended_recipients"] == ("manual-export",)
    assert scope["user_acknowledged_no_final_release"] is True
