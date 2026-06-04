from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import rfq as rfq_endpoint
from app.api.v1.endpoints.rfq import (
    RwdrAnalyzeRequest,
    RwdrBriefRequest,
    RwdrConfirmationDecision,
    RwdrConfirmationsRequest,
    RwdrManufacturerFeedbackItem,
    RwdrManufacturerFeedbackRequest,
    RfqPreviewCreateRequest,
    analyze_rwdr_inquiry,
    record_rwdr_manufacturer_feedback,
    create_rfq_preview,
    diff_rwdr_case_snapshots,
    evaluate_rwdr_case,
    export_rwdr_case_pdf,
    export_rwdr_case_markdown,
    generate_rwdr_brief,
    generate_persisted_rwdr_case_brief,
    get_rwdr_case_snapshot,
    get_rwdr_case,
    get_rfq_preview_export,
    get_rfq_preview_export_pdf,
    rfq_download,
    list_rwdr_case_snapshots,
    update_rwdr_confirmations,
)
from app.models.case_state_snapshot import CaseStateSnapshot
from app.services.auth.dependencies import RequestUser, get_current_request_user
from app.services.rfq_preview_service import (
    RfqExportBlockedError,
    RfqPreviewStaleError,
    RfqPreviewView,
)


def test_rfq_download_is_disabled_even_with_server_path() -> None:
    with pytest.raises(HTTPException) as exc_info:
        rfq_download("/etc/passwd")

    assert exc_info.value.status_code == 410
    assert "temporarily disabled" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_rwdr_analyze_endpoint_returns_source_span_candidates() -> None:
    session = _RwdrFakeSession()
    payload = await analyze_rwdr_inquiry(
        body=RwdrAnalyzeRequest(
            raw_inquiry="Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min."
        ),
        user=_user(),
        session=session,
    )

    assert payload["case_id"]
    candidates = {item["field"]: item for item in payload["evidence_fields"]}
    assert candidates["shaft_diameter_d1_mm"]["source_span"] == "45x62x8"
    assert candidates["shaft_diameter_d1_mm"]["confirmation_status"] == "unconfirmed"
    assert candidates["shaft_diameter_d1_mm"]["origin"] == "llm_extracted"


@pytest.mark.asyncio
async def test_rwdr_case_state_confirmation_evaluate_brief_and_export_endpoints() -> (
    None
):
    session = _RwdrFakeSession()
    created = await analyze_rwdr_inquiry(
        body=RwdrAnalyzeRequest(raw_inquiry="Wellendichtring 45x62x8, Öl, 1500 U/min."),
        user=_user(),
        session=session,
    )
    case_id = created["case_id"]
    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    assert [item["event_type"] for item in listed["snapshots"]] == [
        "case_created_after_analyze",
        "extraction_candidates_stored",
    ]

    updated = await update_rwdr_confirmations(
        case_id=case_id,
        body=RwdrConfirmationsRequest(
            decisions=[
                RwdrConfirmationDecision(
                    field="shaft_diameter_d1_mm",
                    action="confirm",
                    source_span="45x62x8",
                ),
                RwdrConfirmationDecision(
                    field="housing_bore_D_mm", action="confirm", source_span="45x62x8"
                ),
                RwdrConfirmationDecision(
                    field="seal_width_b_mm", action="confirm", source_span="45x62x8"
                ),
                RwdrConfirmationDecision(
                    field="max_speed_rpm", action="confirm", source_span="1500 U/min"
                ),
                RwdrConfirmationDecision(
                    field="pressure_differential", action="explicitly_unknown"
                ),
            ],
        ),
        user=_user(),
        session=session,
    )
    fields = {item["field"]: item for item in updated["evidence_fields"]}
    assert fields["shaft_diameter_d1_mm"]["confirmation_status"] == "confirmed"
    assert (
        fields["pressure_differential"]["confirmation_status"] == "explicitly_unknown"
    )
    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    events = [item["event_type"] for item in listed["snapshots"]]
    assert "confirmation_decision_applied" in events
    assert "field_marked_explicitly_unknown" in events
    assert [item["revision_number"] for item in listed["snapshots"]] == list(
        range(1, len(listed["snapshots"]) + 1)
    )

    initial_diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=1,
        to_revision=1,
        user=_user(),
        session=session,
    )
    assert initial_diff["summary"]["changed_fields_count"] == 0
    assert initial_diff["evidence_field_diffs"] == []

    confirmation_revision = next(
        item["revision_number"]
        for item in listed["snapshots"]
        if item["event_type"] == "confirmation_decision_applied"
    )
    diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=1,
        to_revision=confirmation_revision,
        user=_user(),
        session=session,
    )
    field_diffs = {item["field"]: item for item in diff["evidence_field_diffs"]}
    assert (
        field_diffs["shaft_diameter_d1_mm"]["change_type"]
        == "confirmation_status_changed"
    )
    assert (
        field_diffs["shaft_diameter_d1_mm"]["from"]["confirmation_status"]
        == "unconfirmed"
    )
    assert (
        field_diffs["shaft_diameter_d1_mm"]["to"]["confirmation_status"] == "confirmed"
    )
    assert "shaft_diameter_d1_mm" in diff["missing_critical_fields_diff"]["removed"]
    assert {
        item["field"]
        for item in diff["computed_values_diff"]["added"]
        if isinstance(item, dict)
    } == {"circumferential_speed_mps"}

    reloaded = await get_rwdr_case(case_id=case_id, user=_user(), session=session)
    assert reloaded["case_id"] == case_id
    assert {
        item["field"]: item["confirmation_status"]
        for item in reloaded["evidence_fields"]
    }["shaft_diameter_d1_mm"] == "confirmed"

    evaluation = await evaluate_rwdr_case(
        case_id=case_id, user=_user(), session=session
    )
    assert "computed_values" in evaluation
    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    assert listed["snapshots"][-1]["event_type"] == "evaluation_generated"

    brief = await generate_persisted_rwdr_case_brief(
        case_id=case_id, user=_user(), session=session
    )
    computed = {item["field"]: item for item in brief["calculation_fields"]}
    assert computed["circumferential_speed_mps"]["value"] == 3.53
    assert "pressure_differential" not in {
        item["field"] for item in brief["confirmed_case_fields"]
    }
    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    assert listed["snapshots"][-1]["event_type"] == "technical_brief_generated"

    exported = await export_rwdr_case_markdown(
        case_id=case_id, user=_user(), session=session
    )
    assert exported["case_id"] == case_id
    assert exported["export_format"] == "markdown"
    assert "Technical RWDR RFQ Brief" in exported["content"]
    assert exported["export_metadata"]["revision_number"] == len(session.snapshots)
    snapshot = await get_rwdr_case_snapshot(
        case_id=case_id,
        revision_number=exported["export_metadata"]["revision_number"],
        user=_user(),
        session=session,
    )
    assert snapshot["event_type"] == "markdown_export_generated"
    assert snapshot["snapshot_payload"]["evidence_fields"]

    pdf = await export_rwdr_case_pdf(case_id=case_id, user=_user(), session=session)
    assert pdf.media_type == "application/pdf"
    assert pdf.body.startswith(b"%PDF-")
    assert b"Technical RWDR RFQ Brief" in pdf.body
    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    assert listed["snapshots"][-1]["event_type"] == "pdf_export_generated"
    export_diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=exported["export_metadata"]["revision_number"],
        to_revision=len(session.snapshots),
        user=_user(),
        session=session,
    )
    assert export_diff["export_diff"]["pdf_export_changed"] is True


@pytest.mark.asyncio
async def test_rwdr_manufacturer_feedback_records_open_point_not_confirmed_fact() -> (
    None
):
    """C10: manufacturer feedback persists as candidate, never a confirmed fact, and
    cannot overwrite an already-confirmed field."""
    session = _RwdrFakeSession()
    created = await analyze_rwdr_inquiry(
        body=RwdrAnalyzeRequest(raw_inquiry="Wellendichtring 45x62x8, Öl, 1500 U/min."),
        user=_user(),
        session=session,
    )
    case_id = created["case_id"]
    await update_rwdr_confirmations(
        case_id=case_id,
        body=RwdrConfirmationsRequest(
            decisions=[
                RwdrConfirmationDecision(
                    field="shaft_diameter_d1_mm",
                    action="confirm",
                    source_span="45x62x8",
                ),
            ],
        ),
        user=_user(),
        session=session,
    )

    updated = await record_rwdr_manufacturer_feedback(
        case_id=case_id,
        body=RwdrManufacturerFeedbackRequest(
            responses=[
                RwdrManufacturerFeedbackItem(
                    field="material", value="FKM", note="grenzwertig bei 120 °C"
                ),
                RwdrManufacturerFeedbackItem(
                    field="shaft_diameter_d1_mm",
                    value="46",
                    note="Hersteller schlägt 46 vor",
                ),
            ],
        ),
        user=_user(),
        session=session,
    )

    mfr = [
        f
        for f in updated["evidence_fields"]
        if f.get("source_type") == "manufacturer_response"
    ]
    assert len(mfr) == 2
    assert all(f["validation_status"] == "candidate" for f in mfr)
    assert all(f["confirmation_status"] != "confirmed" for f in mfr)

    # The confirmed field is untouched — the manufacturer response is stored under a
    # namespaced key, so it cannot shadow or overwrite the confirmed value.
    confirmed = [
        f
        for f in updated["evidence_fields"]
        if f["field"] == "shaft_diameter_d1_mm"
        and f.get("source_type") != "manufacturer_response"
    ]
    assert len(confirmed) == 1
    assert confirmed[0]["confirmation_status"] == "confirmed"

    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    assert "manufacturer_response_recorded" in [
        s["event_type"] for s in listed["snapshots"]
    ]


@pytest.mark.asyncio
async def test_rwdr_revision_diff_handles_edit_reject_unknown_and_missing_revisions() -> (
    None
):
    session = _RwdrFakeSession()
    created = await analyze_rwdr_inquiry(
        body=RwdrAnalyzeRequest(raw_inquiry="Wellendichtring 45x62x8, Öl, 1500 U/min."),
        user=_user(),
        session=session,
    )
    case_id = created["case_id"]

    await update_rwdr_confirmations(
        case_id=case_id,
        body=RwdrConfirmationsRequest(
            decisions=[
                RwdrConfirmationDecision(
                    field="shaft_diameter_d1_mm", action="edit", value="46", unit="mm"
                ),
                RwdrConfirmationDecision(
                    field="pressure_differential", action="explicitly_unknown"
                ),
                RwdrConfirmationDecision(field="inside_medium", action="reject"),
            ],
        ),
        user=_user(),
        session=session,
    )
    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    by_event = {
        item["event_type"]: item["revision_number"] for item in listed["snapshots"]
    }
    edit_diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=1,
        to_revision=by_event["evidence_field_edited"],
        user=_user(),
        session=session,
    )
    edit_field = {item["field"]: item for item in edit_diff["evidence_field_diffs"]}[
        "shaft_diameter_d1_mm"
    ]
    assert edit_field["change_type"] in {"confirmation_status_changed", "value_changed"}
    assert edit_field["to"]["value"] == "46"
    assert str(edit_field["to"]["previous_value"]) in {"45", "45.0"}

    unknown_diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=1,
        to_revision=by_event["field_marked_explicitly_unknown"],
        user=_user(),
        session=session,
    )
    assert {
        item["field"]: item["to"].get("confirmation_status")
        for item in unknown_diff["evidence_field_diffs"]
    }["pressure_differential"] == "explicitly_unknown"

    reject_diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=1,
        to_revision=by_event["field_rejected"],
        user=_user(),
        session=session,
    )
    assert {
        item["field"]: item["to"].get("confirmation_status")
        for item in reject_diff["evidence_field_diffs"]
    }["inside_medium"] == "rejected"

    session.snapshots[-1].state_json["snapshot_payload"]["updated_at"] = (
        "2099-01-01T00:00:00Z"
    )
    session.snapshots[-1].state_json["deterministic_payload_json"]["updated_at"] = (
        "2099-01-01T00:00:00Z"
    )
    audit_diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=by_event["field_rejected"],
        to_revision=by_event["field_rejected"],
        user=_user(),
        session=session,
    )
    assert audit_diff["summary"]["changed_fields_count"] == 0
    assert (
        audit_diff["audit_metadata"]["audit_metadata_excluded_from_deterministic_diff"]
        is True
    )

    with pytest.raises(HTTPException) as exc_info:
        await diff_rwdr_case_snapshots(
            case_id=case_id,
            from_revision=1,
            to_revision=999,
            user=_user(),
            session=session,
        )
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as missing_case:
        await diff_rwdr_case_snapshots(
            case_id="missing-case",
            from_revision=1,
            to_revision=2,
            user=_user(),
            session=_RwdrFakeSession(),
        )
    assert missing_case.value.status_code == 404


@pytest.mark.asyncio
async def test_rwdr_case_state_rejects_confirmed_extracted_field_without_source_span() -> (
    None
):
    session = _RwdrFakeSession()
    created = await analyze_rwdr_inquiry(
        body=RwdrAnalyzeRequest(raw_inquiry="Wellendichtring 45x62x8."),
        user=_user(),
        session=session,
    )
    row = session.rows[created["case_id"]]
    fields = []
    for item in row.payload["evidence_fields"]:
        field = dict(item)
        if field.get("field") == "shaft_diameter_d1_mm":
            field.pop("source_span", None)
        fields.append(field)
    row.payload["evidence_fields"] = fields

    with pytest.raises(HTTPException) as exc_info:
        await update_rwdr_confirmations(
            case_id=created["case_id"],
            body=RwdrConfirmationsRequest(
                decisions=[
                    RwdrConfirmationDecision(
                        field="shaft_diameter_d1_mm",
                        action="confirm",
                        source_span="",
                    )
                ],
            ),
            user=_user(),
            session=session,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rwdr_confirmation_invalid"


@pytest.mark.asyncio
async def test_rwdr_brief_endpoint_uses_confirmation_payload() -> None:
    payload = await generate_rwdr_brief(
        body=RwdrBriefRequest(
            raw_inquiry="RWDR Öl",
            fields=[
                {
                    "field": "inside_medium",
                    "value": "Öl",
                    "origin": "llm_extracted",
                    "source_type": "user_text",
                    "status": "confirmed",
                    "validation_status": "confirmed",
                    "confirmation_status": "confirmed",
                    "source_span": "Öl",
                },
                {
                    "field": "temperature_max_c",
                    "value": "80",
                    "origin": "llm_extracted",
                    "source_type": "user_text",
                    "status": "candidate",
                    "validation_status": "candidate",
                    "confirmation_status": "unconfirmed",
                    "source_span": "80 °C",
                },
            ],
        ),
        user=_user(),
    )

    confirmed = {item["field"] for item in payload["confirmed_case_fields"]}
    assert "inside_medium" in confirmed
    assert "temperature_max_c" not in confirmed


@pytest.mark.asyncio
async def test_rfq_preview_create_requires_authenticated_request_user() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_request_user(authorization=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_calls_service_boundary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, session: object) -> None:
            captured["session"] = session

        async def create_preview_for_case(
            self,
            *,
            case_id: str,
            tenant_id: str,
            user_id: str,
            created_by: str,
            expected_case_revision: int | None = None,
        ) -> RfqPreviewView:
            captured.update(
                {
                    "case_id": case_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "created_by": created_by,
                    "expected_case_revision": expected_case_revision,
                }
            )
            return RfqPreviewView(
                preview_id="preview-1",
                case_id=case_id,
                case_revision=4,
                current_case_revision=4,
                stale=False,
                consent_status="not_requested",
                dispatch_enabled=False,
                payload={"meta": {"artifact_type": "rfq_preview", "case_revision": 4}},
                created_at=None,
            )

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    payload = await create_rfq_preview(
        raw_request=_Request(),
        body=RfqPreviewCreateRequest(
            action="create_preview",
            explicit_user_intent=True,
            expected_case_revision=4,
        ),
        case_id="case-123",
        user=_user(),
        session=object(),
    )

    assert captured["case_id"] == "case-123"
    assert captured["tenant_id"] == "tenant-1"
    assert captured["user_id"] == "user-1"
    assert captured["created_by"] == "user-1"
    assert captured["expected_case_revision"] == 4
    assert payload["preview_id"] == "preview-1"
    assert payload["case_revision"] == 4
    assert payload["dispatch_enabled"] is False
    assert payload["dispatch_allowed"] is False
    assert payload["external_contact_allowed"] is False
    assert payload["preview_action"] == "create_rfq_preview"
    assert (
        payload["preview_service_boundary"]
        == "RfqPreviewService.create_preview_for_case"
    )
    gate = payload["qualified_action_gate"]
    assert gate["preview_creation_requires_explicit_user_intent"] is True
    assert gate["export_requires_consent"] is True
    assert gate["dispatch_allowed"] is False
    assert gate["external_contact_allowed"] is False
    contract = payload["result_contract"]
    assert contract["artifact_type"] == "rfq_preview"
    assert contract["action"] == "create_rfq_preview"
    assert contract["no_external_dispatch"] is True


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_requires_explicit_user_intent() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_rfq_preview(
            raw_request=_Request(),
            body=RfqPreviewCreateRequest(
                action="create_preview",
                explicit_user_intent=False,
            ),
            case_id="case-123",
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rfq_preview_explicit_intent_required"


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_rejects_dispatch_flags() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_rfq_preview(
            raw_request=_Request(),
            body=RfqPreviewCreateRequest(
                action="create_preview",
                explicit_user_intent=True,
                dispatch_allowed=True,
            ),
            case_id="case-123",
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rfq_preview_external_dispatch_not_allowed"


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_maps_expected_revision_mismatch(
    monkeypatch,
) -> None:
    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def create_preview_for_case(self, **_kwargs: object) -> object:
            raise RfqPreviewStaleError(
                "case revision changed; refresh before creating preview"
            )

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    with pytest.raises(HTTPException) as exc_info:
        await create_rfq_preview(
            raw_request=_Request(),
            body=RfqPreviewCreateRequest(
                action="create_preview",
                explicit_user_intent=True,
                expected_case_revision=3,
            ),
            case_id="case-123",
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "rfq_preview_stale"


@pytest.mark.asyncio
async def test_rfq_preview_export_endpoint_returns_manual_json_contract(
    monkeypatch,
) -> None:
    class FakeExportDocument:
        def as_dict(self) -> dict[str, object]:
            return {
                "export_generated": True,
                "preview_id": "preview-1",
                "case_revision": 4,
                "artifact_type": "rfq_preview",
                "export_format": "json",
                "dispatch_enabled": False,
                "automatic_dispatch_allowed": False,
                "no_final_technical_release": True,
                "event_names": (
                    "RFQConsentGranted",
                    "ExportGenerated",
                    "ExternalDispatchBlocked",
                    "RFQDispatchDisabled",
                ),
                "content": {"title": "RFQ Preview"},
            }

    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def generate_export(
            self,
            *,
            preview_id: str,
            tenant_id: str,
            user_id: str,
        ) -> FakeExportDocument:
            assert preview_id == "preview-1"
            assert tenant_id == "tenant-1"
            assert user_id == "user-1"
            return FakeExportDocument()

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    payload = await get_rfq_preview_export(
        preview_id="preview-1",
        raw_request=_Request(),
        user=_user(),
        session=object(),
    )

    assert payload["export_generated"] is True
    assert payload["artifact_type"] == "rfq_preview"
    assert payload["dispatch_enabled"] is False
    assert payload["automatic_dispatch_allowed"] is False
    assert "ExternalDispatchBlocked" in payload["event_names"]


@pytest.mark.asyncio
async def test_rfq_preview_export_pdf_endpoint_returns_allowlisted_pdf(
    monkeypatch,
) -> None:
    class FakeExportDocument:
        preview_id = "preview-1"
        case_id = "case-123"

        def as_dict(self) -> dict[str, object]:
            return {
                "export_generated": True,
                "preview_id": self.preview_id,
                "case_id": self.case_id,
                "case_revision": 4,
                "artifact_type": "rfq_preview",
                "export_format": "json",
                "dispatch_enabled": False,
                "automatic_dispatch_allowed": False,
                "no_final_technical_release": True,
                "event_names": (
                    "RFQConsentGranted",
                    "ExportGenerated",
                    "ExternalDispatchBlocked",
                    "RFQDispatchDisabled",
                ),
                "content": {
                    "title": "RFQ Preview",
                    "safe_case_reference": {"case_id": self.case_id},
                    "preview_reference": {"preview_id": self.preview_id},
                    "revision": {"case_revision": 4},
                    "technical_fields": [
                        {
                            "field": "medium_name",
                            "value": "HLP 46",
                            "status": "confirmed",
                            "provenance": "user",
                            "confidence": "confirmed",
                        }
                    ],
                    "manufacturer_review_notes": [
                        "Bitte Medienbestaendigkeit und Einsatzgrenzen pruefen."
                    ],
                },
            }

    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def generate_export(
            self,
            *,
            preview_id: str,
            tenant_id: str,
            user_id: str,
        ) -> FakeExportDocument:
            assert preview_id == "preview-1"
            assert tenant_id == "tenant-1"
            assert user_id == "user-1"
            return FakeExportDocument()

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    response = await get_rfq_preview_export_pdf(
        preview_id="preview-1",
        raw_request=_Request(),
        user=_user(),
        session=object(),
    )

    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF-")
    assert b"Anfragebasis fuer Herstellerpruefung" in response.body
    assert b"HLP 46" in response.body
    assert response.headers["content-disposition"].endswith(
        'filename="sealai-rfq-case-123-preview-1.pdf"'
    )
    assert response.headers["x-sealai-dispatch-allowed"] == "false"
    assert response.headers["x-sealai-external-contact-allowed"] == "false"


@pytest.mark.asyncio
async def test_rfq_preview_export_endpoint_maps_blocked_export(monkeypatch) -> None:
    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def generate_export(self, **_kwargs: object) -> object:
            raise RfqExportBlockedError("RFQ preview consent is required before export")

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    with pytest.raises(HTTPException) as exc_info:
        await get_rfq_preview_export(
            preview_id="preview-1",
            raw_request=_Request(),
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "rfq_export_blocked"
    assert "ExportBlocked" in exc_info.value.detail["event_names"]
    assert "ExternalDispatchBlocked" in exc_info.value.detail["event_names"]


class _Request:
    headers: dict[str, str] = {}


class _ScalarResult:
    def __init__(
        self, row: object | None = None, rows: list[object] | None = None
    ) -> None:
        self.row = row
        self.rows = rows or ([] if row is None else [row])

    def scalar_one_or_none(self) -> object | None:
        return self.row

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> list[object]:
        return list(self.rows)


class _RwdrFakeSession:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}
        self.snapshots: list[CaseStateSnapshot] = []

    def add(self, row: object) -> None:
        if isinstance(row, CaseStateSnapshot):
            self.snapshots.append(row)
        else:
            self.rows[str(row.id)] = row

    async def commit(self) -> None:
        return None

    async def execute(self, _statement: object) -> _ScalarResult:
        row = next(iter(self.rows.values()), None)
        return _ScalarResult(row)


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="user-1",
        sub="user-1",
        roles=[],
        tenant_id="tenant-1",
    )


# --- Patch 1: /rwdr/cases/* derive + forward authenticated owner scope -------
#
# The endpoints must derive tenant_id (via _request_tenant_id) and user_id from
# the authenticated request user and forward them into the persisted-case
# repository, and must map the repository's ownership miss
# (RWDRCaseStateNotFound) to a 404 with no existence leak. The SQL ownership
# guard itself is exercised against a real DB in
# tests/unit/services/test_rwdr_mvp_brief_tenant_scope.py.

from app.services.rwdr_mvp_brief import RWDRCaseStateNotFound as _RWDRCaseStateNotFound


@pytest.mark.asyncio
async def test_get_rwdr_case_forwards_authenticated_owner_scope(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_get(*, session, case_id, tenant_id, user_id):
        captured.update(case_id=case_id, tenant_id=tenant_id, user_id=user_id)
        return {"case_id": case_id}

    monkeypatch.setattr(rfq_endpoint, "get_db_persisted_rwdr_case", _fake_get)

    result = await get_rwdr_case(case_id="case-1", user=_user(), session=object())

    assert result["case_id"] == "case-1"
    assert captured == {
        "case_id": "case-1",
        "tenant_id": "tenant-1",
        "user_id": "user-1",
    }


@pytest.mark.asyncio
async def test_get_rwdr_case_maps_ownership_miss_to_404(monkeypatch) -> None:
    async def _fake_get(**_kwargs):
        raise _RWDRCaseStateNotFound("case-1")

    monkeypatch.setattr(rfq_endpoint, "get_db_persisted_rwdr_case", _fake_get)

    with pytest.raises(HTTPException) as exc_info:
        await get_rwdr_case(case_id="case-1", user=_user(), session=object())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "rwdr_case_not_found"


@pytest.mark.asyncio
async def test_update_confirmations_forwards_authenticated_owner_scope(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_update(*, session, case_id, decisions, tenant_id, user_id):
        captured.update(case_id=case_id, tenant_id=tenant_id, user_id=user_id)
        return {"case_id": case_id, "evidence_fields": []}

    monkeypatch.setattr(
        rfq_endpoint, "update_db_persisted_rwdr_confirmations", _fake_update
    )

    await update_rwdr_confirmations(
        case_id="case-1",
        body=RwdrConfirmationsRequest(decisions=[]),
        user=_user(),
        session=object(),
    )

    assert captured == {
        "case_id": "case-1",
        "tenant_id": "tenant-1",
        "user_id": "user-1",
    }
