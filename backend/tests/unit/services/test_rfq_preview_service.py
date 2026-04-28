from __future__ import annotations

import pytest

from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.models.inquiry_extract import InquiryExtractModel
from app.services.rfq_preview_service import (
    RFQ_PREVIEW_SECTIONS,
    RfqPreviewError,
    RfqPreviewNotFound,
    RfqPreviewService,
    RfqPreviewStaleError,
    _view,
    build_rfq_preview_payload,
    collect_open_points,
    collect_technical_field_statuses,
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


def _snapshot_with_field_statuses() -> CaseStateSnapshot:
    return CaseStateSnapshot(
        case_id="case-123",
        revision=4,
        state_json={
            "case_state": {
                "medium_name": {
                    "canonical_value": "Salzwasser",
                    "status": "documented",
                    "provenance": "upload:datasheet-1",
                    "confidence": 0.86,
                    "confirmation_required": False,
                },
                "pressure_nominal": {
                    "canonical_value": 4,
                    "unit": "bar",
                    "status": "candidate",
                    "provenance": "user",
                    "confidence": 0.62,
                    "confirmation_required": True,
                },
                "shaft_diameter": {
                    "canonical_value": 42,
                    "unit": "mm",
                    "status": "inferred",
                    "requires_confirmation": True,
                },
            }
        },
    )


def _snapshot_with_field_envelopes() -> CaseStateSnapshot:
    return CaseStateSnapshot(
        case_id="case-123",
        revision=4,
        state_json={
            "case_state": {
                "case_fields": {
                    "speed_rpm": {
                        "field_name": "speed_rpm",
                        "value": 1450,
                        "engineering_value": {
                            "raw_value": "1450 rpm",
                            "canonical_value": 1450,
                            "unit": "rpm",
                            "quantity_kind": "rotational_speed",
                        },
                        "status": "confirmed",
                        "provenance": "confirmed",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                        "source_revision": 4,
                    },
                    "medium_name": {
                        "field_name": "medium_name",
                        "value": "Salzwasser",
                        "status": "documented",
                        "provenance": "documented",
                        "evidence_refs": ["upload:datasheet-1#p2"],
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "motion_type": {
                        "field_name": "motion_type",
                        "value": "rotary",
                        "status": "user_stated",
                        "provenance": "user_stated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "shaft_diameter_mm": {
                        "field_name": "shaft_diameter_mm",
                        "value": 42,
                        "engineering_value": {
                            "canonical_value": 42,
                            "unit": "mm",
                            "quantity_kind": "length",
                        },
                        "status": "inferred",
                        "provenance": "inferred",
                        "confidence": "inferred",
                        "confirmation_required": True,
                    },
                    "calculated_speed_m_s": {
                        "field_name": "calculated_speed_m_s",
                        "value": 3.19,
                        "engineering_value": {
                            "canonical_value": 3.19,
                            "unit": "m/s",
                            "quantity_kind": "surface_speed",
                        },
                        "status": "confirmed",
                        "provenance": "calculated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "pressure_bar": {
                        "field_name": "pressure_bar",
                        "value": 4,
                        "engineering_value": {
                            "canonical_value": 4,
                            "unit": "bar",
                            "quantity_kind": "pressure",
                            "interpretation": "unknown",
                        },
                        "status": "conflict",
                        "provenance": "user_stated",
                        "confidence": "requires_confirmation",
                        "confirmation_required": True,
                        "evidence_refs": ["chat:turn-3", "upload:datasheet-2#p1"],
                    },
                },
                "missing_required_fields": ["shaft_surface_finish"],
                "top_risks": ["pressure_conflict"],
                "manufacturer_review_needs": ["Druckangabe und Oberflaeche klaeren"],
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


def test_rfq_preview_groups_casefield_envelopes_by_status_and_provenance() -> None:
    payload = build_rfq_preview_payload(
        case_row=_case(),
        snapshot=_snapshot_with_field_envelopes(),
    )
    preview = payload["rfq_preview"]
    groups = {
        group["key"]: {field["field"]: field for field in group["fields"]}
        for group in preview["technical_field_groups"]
    }

    assert groups["confirmed"]["speed_rpm"]["value"] == 1450
    assert groups["documented"]["medium_name"]["evidence_refs"] == (
        "upload:datasheet-1#p2",
    )
    assert groups["user_stated"]["motion_type"]["value"] == "rotary"
    assert groups["inferred"]["shaft_diameter_mm"]["confirmation_required"] is True
    assert groups["calculated"]["calculated_speed_m_s"]["engineering_value"][
        "unit"
    ] == "m/s"
    assert groups["conflicting"]["pressure_bar"]["evidence_refs"] == (
        "chat:turn-3",
        "upload:datasheet-2#p1",
    )
    assert groups["missing"]["shaft_surface_finish"]["value"] is None
    assert groups["needs_confirmation"]["pressure_bar"]["status"] == "conflict"
    assert groups["needs_confirmation"]["shaft_surface_finish"]["status"] == "missing"
    assert "shaft_surface_finish" in preview["confirmation_required_fields"]
    assert "pressure_bar" in preview["confirmation_required_fields"]


def test_rfq_preview_sections_render_critical_values_as_envelopes() -> None:
    payload = build_rfq_preview_payload(
        case_row=_case(),
        snapshot=_snapshot_with_field_envelopes(),
    )
    operating_data = next(
        section
        for section in payload["rfq_preview"]["sections"]
        if section["title"] == "Betriebsdaten"
    )
    calculations = next(
        section
        for section in payload["rfq_preview"]["sections"]
        if section["title"] == "Berechnungen / technische Hinweise"
    )

    assert operating_data["content"]["pressure_bar"] == {
        "value": 4,
        "unit": "bar",
        "status": "conflict",
        "provenance": "user_stated",
        "confirmation_required": True,
        "evidence_refs": ("chat:turn-3", "upload:datasheet-2#p1"),
    }
    assert calculations["content"]["calculated_speed_m_s"] == {
        "value": 3.19,
        "unit": "m/s",
        "status": "confirmed",
        "provenance": "calculated",
        "confirmation_required": False,
    }


def test_rfq_preview_release_boundary_is_review_oriented_not_compliance_approval() -> None:
    payload = build_rfq_preview_payload(
        case_row=_case(),
        snapshot=_snapshot_with_field_envelopes(),
    )

    boundary = payload["rfq_preview"]["manufacturer_release_boundary"]

    assert "manufacturer review" in boundary
    assert "no final technical release" in boundary
    assert "no compliance approval" in boundary
    assert "FDA-konform" not in boundary
    assert "ATEX-zertifiziert" not in boundary
    assert "final freigegeben" not in boundary


def test_collects_technical_field_statuses_without_changing_values() -> None:
    snapshot = _snapshot_with_field_statuses()

    fields = collect_technical_fields(case_row=_case(), state=snapshot.state_json)
    statuses = collect_technical_field_statuses(snapshot.state_json)

    assert fields["medium_name"] == "Salzwasser"
    assert fields["pressure_bar"] == 4
    assert fields["shaft_diameter_mm"] == 42
    assert {
        "field": "medium_name",
        "status": "documented",
        "provenance": "upload:datasheet-1",
        "confidence": "0.86",
        "confirmation_required": False,
    } in statuses
    assert {
        "field": "pressure_bar",
        "status": "candidate",
        "provenance": "user",
        "confidence": "0.62",
        "confirmation_required": True,
    } in statuses


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


def test_rfq_preview_marks_unconfirmed_fields_as_open_points_not_release() -> None:
    payload = build_rfq_preview_payload(
        case_row=_case(),
        snapshot=_snapshot_with_field_statuses(),
    )

    assert payload["meta"]["case_revision"] == 4
    assert payload["rfq_preview"]["confirmation_required_fields"] == (
        "pressure_bar",
        "shaft_diameter_mm",
    )
    assert {
        "field": "pressure_bar",
        "status": "candidate",
        "provenance": "user",
        "confidence": "0.62",
        "confirmation_required": True,
    } in payload["rfq_preview"]["technical_field_statuses"]
    assert any(
        "Bestaetigung erforderlich: pressure_bar" in item
        for item in payload["manufacturer_extract"]["open_points"]
    )
    assert (
        payload["consent_boundary"]["open_points_acknowledgement_required"] is True
    )
    release_boundary = payload["rfq_preview"]["manufacturer_release_boundary"].lower()
    assert "no final technical release" in release_boundary
    assert "approved" not in release_boundary


def test_manufacturer_extract_is_allowlisted_and_revision_bound() -> None:
    payload = build_rfq_preview_payload(case_row=_case(), snapshot=_snapshot())
    extract = payload["manufacturer_extract"]

    assert extract["meta"]["artifact_type"] == "rfq_preview"
    assert extract["meta"]["case_revision"] == 4
    assert extract["technical_parameters"]["medium_name"] == "Salzwasser"
    assert "customer_metadata" not in extract
    assert extract["privacy_boundary"]["mode"] == "allowlist"


def test_rfq_preview_does_not_require_matching_or_manufacturer_shortlist() -> None:
    snapshot = _snapshot()
    snapshot.state_json["case_state"]["matching"] = {
        "items": [{"manufacturer": "ShouldNotBeRequired"}],
        "manufacturer_shortlist": ["ShouldNotLeak"],
    }

    payload = build_rfq_preview_payload(case_row=_case(), snapshot=snapshot)

    assert payload["meta"]["artifact_type"] == "rfq_preview"
    assert payload["consent_boundary"]["automatic_dispatch_allowed"] is False
    assert "matching" not in payload["rfq_preview"]
    assert "manufacturer_shortlist" not in payload["rfq_preview"]
    assert "manufacturer_shortlist" not in payload["manufacturer_extract"]


def test_rfq_preview_view_is_stale_when_case_revision_changes() -> None:
    row = InquiryExtractModel(
        extract_id="preview-1",
        case_id="case-123",
        tenant_id="tenant-1",
        case_revision=4,
        artifact_type="rfq_preview",
        payload={"meta": {"case_revision": 4}},
        source_kind="case_revision",
        consent_status="not_requested",
        consent_scope={},
        dispatch_enabled=False,
    )

    view = _view(row, current_case_revision=5)

    assert view.case_revision == 4
    assert view.current_case_revision == 5
    assert view.stale is True
    assert view.dispatch_enabled is False


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


def test_consent_scope_requires_no_final_release_acknowledgement() -> None:
    with pytest.raises(RfqPreviewError, match="user_acknowledged_no_final_release"):
        normalize_consent_scope(
            {
                "shared_sections": ["rfq_preview"],
                "user_acknowledged_open_points": True,
            }
        )


def test_consent_scope_requires_open_points_acknowledgement_when_needed() -> None:
    with pytest.raises(RfqPreviewError, match="user_acknowledged_open_points"):
        normalize_consent_scope(
            {
                "shared_sections": ["rfq_preview"],
                "user_acknowledged_no_final_release": True,
            },
            open_points_acknowledgement_required=True,
        )


def test_consent_scope_accepts_valid_acknowledgements_and_ignores_dispatch_flag() -> None:
    scope = normalize_consent_scope(
        {
            "shared_sections": ["rfq_preview"],
            "shared_documents": [],
            "intended_recipients": ["manual-export"],
            "user_acknowledged_open_points": True,
            "user_acknowledged_no_final_release": True,
            "dispatch_enabled": True,
        },
        open_points_acknowledgement_required=True,
    )

    assert scope == {
        "shared_sections": ("rfq_preview",),
        "shared_documents": (),
        "intended_recipients": ("manual-export",),
        "user_acknowledged_open_points": True,
        "user_acknowledged_no_final_release": True,
    }
    assert "dispatch_enabled" not in scope


@pytest.mark.asyncio
async def test_grant_preview_consent_rejects_stale_preview() -> None:
    preview = InquiryExtractModel(
        extract_id="preview-1",
        case_id="case-123",
        tenant_id="tenant-1",
        case_revision=4,
        artifact_type="rfq_preview",
        payload={
            "meta": {"case_revision": 4},
            "consent_boundary": {
                "open_points_acknowledgement_required": False,
            },
        },
        source_kind="case_revision",
        consent_status="not_requested",
        consent_scope={},
        dispatch_enabled=False,
    )
    case_row = _case()
    case_row.case_revision = 5
    service = RfqPreviewService(_FakeConsentSession([preview, case_row]))

    with pytest.raises(RfqPreviewStaleError):
        await service.grant_preview_consent(
            preview_id="preview-1",
            tenant_id="tenant-1",
            user_id="user-1",
            granted_by="user-1",
            consent_scope={
                "shared_sections": ["rfq_preview"],
                "user_acknowledged_no_final_release": True,
            },
        )

    assert preview.consent_status == "not_requested"
    assert preview.dispatch_enabled is False


@pytest.mark.asyncio
async def test_grant_preview_consent_keeps_dispatch_disabled() -> None:
    preview = InquiryExtractModel(
        extract_id="preview-1",
        case_id="case-123",
        tenant_id="tenant-1",
        case_revision=4,
        artifact_type="rfq_preview",
        payload={
            "meta": {"case_revision": 4},
            "consent_boundary": {
                "open_points_acknowledgement_required": True,
            },
        },
        source_kind="case_revision",
        consent_status="not_requested",
        consent_scope={},
        dispatch_enabled=False,
    )
    service = RfqPreviewService(_FakeConsentSession([preview, _case()]))

    view = await service.grant_preview_consent(
        preview_id="preview-1",
        tenant_id="tenant-1",
        user_id="user-1",
        granted_by="user-1",
        consent_scope={
            "shared_sections": ["rfq_preview"],
            "user_acknowledged_open_points": True,
            "user_acknowledged_no_final_release": True,
            "dispatch_enabled": True,
        },
    )

    assert view.consent_status == "granted"
    assert view.dispatch_enabled is False
    assert preview.dispatch_enabled is False
    assert preview.payload["consent_boundary"]["automatic_dispatch_allowed"] is False
    assert preview.payload["consent_boundary"]["phase"] == "phase_1_preview_export_only"


@pytest.mark.asyncio
async def test_grant_preview_consent_rejects_cross_tenant_preview_id() -> None:
    preview = InquiryExtractModel(
        extract_id="preview-1",
        case_id="case-123",
        tenant_id="tenant-2",
        case_revision=4,
        artifact_type="rfq_preview",
        payload={
            "meta": {"case_revision": 4},
            "consent_boundary": {
                "open_points_acknowledgement_required": False,
            },
        },
        source_kind="case_revision",
        consent_status="not_requested",
        consent_scope={},
        dispatch_enabled=False,
    )
    service = RfqPreviewService(_FilteringPreviewSession([preview, _case()]))

    with pytest.raises(RfqPreviewNotFound):
        await service.grant_preview_consent(
            preview_id="preview-1",
            tenant_id="tenant-1",
            user_id="user-1",
            granted_by="user-1",
            consent_scope={
                "shared_sections": ["rfq_preview"],
                "user_acknowledged_no_final_release": True,
            },
        )

    assert preview.consent_status == "not_requested"


@pytest.mark.asyncio
async def test_get_latest_preview_rejects_cross_tenant_case_id() -> None:
    service = RfqPreviewService(_FilteringPreviewSession([_case()]))

    with pytest.raises(RfqPreviewNotFound):
        await service.get_latest_preview_for_case(
            case_id="case-123",
            tenant_id="tenant-2",
            user_id="user-1",
        )

class _FakeScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakeConsentSession:
    def __init__(self, results: list[object]) -> None:
        self._results = list(results)

    async def execute(self, _statement: object) -> _FakeScalarResult:
        return _FakeScalarResult(self._results.pop(0))

    async def commit(self) -> None:
        return None

    async def refresh(self, _row: object) -> None:
        return None


class _FilteringPreviewSession(_FakeConsentSession):
    async def execute(self, statement: object) -> _FakeScalarResult:
        rows = list(self._results)
        for criterion in getattr(statement, "_where_criteria", []):
            left = getattr(criterion, "left", None)
            right = getattr(criterion, "right", None)
            field_name = getattr(left, "name", None)
            expected = getattr(right, "value", None)
            rows = [row for row in rows if getattr(row, field_name, None) == expected]
        return _FakeScalarResult(rows[0] if rows else None)
