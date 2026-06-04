from __future__ import annotations

import inspect

import pytest

from app.services import inquiry_extract_service as service_module
from app.services.inquiry_extract_service import (
    ALLOWED_TECHNICAL_FIELD_PATHS,
    DEFAULT_ARTIFACT_TYPE,
    DEFAULT_SOURCE_KIND,
    EXTRACT_SCHEMA_VERSION,
    InquiryExtractService,
    InquiryExtractValidationError,
    build_inquiry_extract,
    build_inquiry_extract_payload,
    validate_manufacturer_view,
)


@pytest.fixture
def service() -> InquiryExtractService:
    return InquiryExtractService()


def _base_context(**overrides):
    context = {
        "case_id": "case-123",
        "tenant_id": "tenant-user-1",
        "case_revision": 7,
        "request_type": "retrofit",
        "engineering_path": "rwdr",
        "sealing_material_family": "ptfe_carbon_filled",
        "technical_fields": {
            "shaft_diameter_mm": 42,
            "housing_bore_diameter_mm": 62,
            "seal_width_mm": 10,
            "medium_name": "water-glycol",
            "pressure_bar": 4.5,
            "customer_email": "buyer@example.com",
            "project_code": "secret-project",
        },
        "missing_fields": ["shaft_surface_finish", "lead_time_criticality"],
        "norm_results": [
            {
                "module_id": "norm_din_3760_iso_6194",
                "version": "1.0.0",
                "status": "review_required",
                "applies": True,
                "missing_required_fields": ["shaft_surface_finish"],
                "references": ["DIN 3760", "ISO 6194"],
                "finding_text": "internal diagnostic not for extract",
            }
        ],
        "advisory_results": [
            {
                "advisory_id": "adv_norm_review_required",
                "category": "norm_compliance_alert",
                "severity": "caution",
                "reason_code": "norm_review_required",
                "triggering_parameters": ["norm_din_3760_iso_6194"],
                "evidence_tags": ["norm_modules"],
                "blocking": False,
                "message": "free advisory prose is not copied",
            }
        ],
        "article_references": [
            {
                "reference_type": "manufacturer_part_number",
                "value": "MFR-PTFE-42",
                "source": "user_confirmed",
                "manufacturer_visible": True,
            },
            {
                "reference_type": "customer_internal_article_number",
                "value": "CUST-SECRET-001",
                "manufacturer_visible": True,
            },
        ],
        "manufacturer_facing_notes": [
            {
                "note_type": "installation_constraint",
                "note_code": "fixed_housing_bore",
                "text": "Do not copy this free text.",
                "approved_for_manufacturer": True,
            }
        ],
        "customer_metadata": {"company": "Secret GmbH"},
        "free_text_notes": "Call Max at max@example.com",
    }
    context.update(overrides)
    return context


def test_build_success_for_clean_technical_context(service: InquiryExtractService) -> None:
    extract = service.build_inquiry_extract(_base_context())

    assert extract.case_id == "case-123"
    assert extract.tenant_id == "tenant-user-1"
    assert extract.dispatched_to_manufacturer_id is None
    assert extract.case_revision == 7
    assert extract.artifact_type == DEFAULT_ARTIFACT_TYPE
    assert extract.source_kind == DEFAULT_SOURCE_KIND
    assert extract.payload["meta"]["schema_version"] == EXTRACT_SCHEMA_VERSION


def test_dispatch_target_is_persistable_metadata_not_payload(
    service: InquiryExtractService,
) -> None:
    extract = service.build_inquiry_extract(
        _base_context(dispatched_to_manufacturer_id="mfr-target-1")
    )

    assert extract.dispatched_to_manufacturer_id == "mfr-target-1"
    assert "dispatched_to_manufacturer_id" not in extract.payload["meta"]


def test_build_payload_helper_matches_service_payload(service: InquiryExtractService) -> None:
    context = _base_context()

    assert build_inquiry_extract_payload(context) == service.build_inquiry_extract_payload(context)
    assert build_inquiry_extract(context).payload == service.build_inquiry_extract_payload(context)


def test_request_type_engineering_path_and_material_family_are_projected(
    service: InquiryExtractService,
) -> None:
    payload = service.build_inquiry_extract_payload(_base_context())

    assert payload["technical_scope"] == {
        "request_type": "retrofit",
        "engineering_path": "rwdr",
        "sealing_material_family": "ptfe_carbon_filled",
    }


def test_missing_fields_are_projected_as_open_points(service: InquiryExtractService) -> None:
    payload = service.build_inquiry_extract_payload(_base_context())

    assert payload["open_points"] == ("shaft_surface_finish", "lead_time_criticality")


def test_norm_summary_is_controlled(service: InquiryExtractService) -> None:
    payload = service.build_inquiry_extract_payload(_base_context())

    norm = payload["norm_compliance_signals"][0]
    assert norm["module_id"] == "norm_din_3760_iso_6194"
    assert norm["status"] == "review_required"
    assert norm["references"] == ("DIN 3760", "ISO 6194")
    assert "finding_text" not in norm


def test_advisory_summary_is_controlled(service: InquiryExtractService) -> None:
    payload = service.build_inquiry_extract_payload(_base_context())

    advisory = payload["advisory_summary"][0]
    assert advisory["advisory_id"] == "adv_norm_review_required"
    assert advisory["category"] == "norm_compliance_alert"
    assert advisory["blocking"] is False
    assert "message" not in advisory


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("application_pattern", "chemical_process_pump"),
        ("atex_required", True),
        ("calculated_pv_mpa_m_s", 1.2),
        ("calculated_speed_m_s", 8.1),
        ("cleaning_regime", "cip"),
        ("duty_cycle", "continuous"),
        ("equipment_type", "pump"),
        ("food_contact_required", False),
        ("housing_bore_diameter_mm", 62),
        ("installation_space_axial_mm", 12),
        ("installation_space_radial_mm", 8),
        ("lead_time_criticality", "normal"),
        ("lubrication_state", "mixed"),
        ("medium_concentration", "30%"),
        ("medium_name", "water"),
        ("medium_temperature_c", 80),
        ("motion_type", "rotary"),
        ("operating_hours_per_day", 16),
        ("pressure_bar", 3),
        ("production_mode", "spare_part"),
        ("quantity_requested", 4),
        ("seal_type", "A"),
        ("seal_width_mm", 10),
        ("shaft_diameter_mm", 42),
        ("shaft_hardness_hrc", 60),
        ("shaft_lead_present", False),
        ("shaft_surface_finish", "Ra 0.2"),
        ("speed_rpm", 1500),
        ("temperature_c", 80),
        ("temperature_max_c", 120),
        ("temperature_min_c", -20),
    ],
)
def test_allowed_technical_fields_are_included(
    service: InquiryExtractService,
    field_name: str,
    value,
) -> None:
    payload = service.build_inquiry_extract_payload(
        _base_context(technical_fields={field_name: value})
    )

    assert field_name in ALLOWED_TECHNICAL_FIELD_PATHS
    assert payload["technical_parameters"][field_name] == value


@pytest.mark.parametrize(
    "field_name",
    [
        "customer_email",
        "customer_name",
        "contact_phone",
        "project_code",
        "raw_user_text",
        "photo_exif",
        "session_id",
        "billing_address",
        "customer_internal_article_number",
        "conversation_history",
    ],
)
def test_direct_pii_or_customer_specific_technical_fields_are_not_included(
    service: InquiryExtractService,
    field_name: str,
) -> None:
    payload = service.build_inquiry_extract_payload(
        _base_context(technical_fields={"shaft_diameter_mm": 42, field_name: "secret"})
    )

    assert field_name not in payload["technical_parameters"]
    assert payload["technical_parameters"] == {"shaft_diameter_mm": 42}


@pytest.mark.parametrize(
    "root_key",
    [
        "customer_metadata",
        "internal_metadata",
        "free_text_notes",
        "conversation_history",
        "contact",
        "photos",
        "media",
        "raw_uploads",
    ],
)
def test_customer_or_internal_root_metadata_is_not_copied(
    service: InquiryExtractService,
    root_key: str,
) -> None:
    payload = service.build_inquiry_extract_payload(_base_context(**{root_key: {"secret": True}}))

    assert root_key not in payload


@pytest.mark.parametrize(
    ("reference_type", "manufacturer_visible", "expected_included"),
    [
        ("manufacturer_part_number", True, True),
        ("standard_designation", True, True),
        ("public_datasheet_reference", True, True),
        ("drawing_reference", True, True),
        ("manufacturer_part_number", False, False),
        ("customer_internal_article_number", True, False),
        ("customer_project_code", True, False),
    ],
)
def test_article_reference_boundary(
    service: InquiryExtractService,
    reference_type: str,
    manufacturer_visible: bool,
    expected_included: bool,
) -> None:
    payload = service.build_inquiry_extract_payload(
        _base_context(
            article_references=[
                {
                    "reference_type": reference_type,
                    "value": "REF-123",
                    "manufacturer_visible": manufacturer_visible,
                }
            ]
        )
    )

    references = payload.get("article_references", ())
    assert bool(references) is expected_included


def test_customer_article_number_from_unapproved_field_is_not_included(
    service: InquiryExtractService,
) -> None:
    payload = service.build_inquiry_extract_payload(
        _base_context(
            article_references=[
                {
                    "reference_type": "customer_internal_article_number",
                    "value": "CUST-4711",
                    "manufacturer_visible": True,
                }
            ]
        )
    )

    assert "article_references" not in payload


def test_explicit_neutral_article_reference_is_included(service: InquiryExtractService) -> None:
    payload = service.build_inquiry_extract_payload(
        _base_context(
            article_references=[
                {
                    "reference_type": "manufacturer_part_number",
                    "value": "MFR-42",
                    "source": "datasheet",
                    "manufacturer_visible": True,
                }
            ]
        )
    )

    assert payload["article_references"] == (
        {
            "reference_type": "manufacturer_part_number",
            "value": "MFR-42",
            "source": "datasheet",
        },
    )


def test_free_note_text_is_not_copied_even_when_note_is_approved(
    service: InquiryExtractService,
) -> None:
    payload = service.build_inquiry_extract_payload(_base_context())

    assert payload["manufacturer_facing_notes"] == (
        {
            "note_type": "installation_constraint",
            "note_code": "fixed_housing_bore",
        },
    )


def test_unapproved_manufacturer_note_is_not_included(service: InquiryExtractService) -> None:
    payload = service.build_inquiry_extract_payload(
        _base_context(
            manufacturer_facing_notes=[
                {
                    "note_type": "installation_constraint",
                    "note_code": "fixed_housing_bore",
                    "approved_for_manufacturer": False,
                }
            ]
        )
    )

    assert "manufacturer_facing_notes" not in payload


def test_optional_fields_can_be_missing_without_breaking(service: InquiryExtractService) -> None:
    payload = service.build_inquiry_extract_payload(
        {
            "case_id": "case-min",
            "tenant_id": "tenant-a",
            "case_revision": 0,
        }
    )

    assert payload["meta"]["case_id"] == "case-min"
    assert "technical_scope" not in payload
    assert "technical_parameters" not in payload


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("case_id", "", "case_id is required"),
        ("tenant_id", "", "tenant_id is required"),
        ("case_revision", None, "case_revision is required"),
        ("case_revision", "bad", "case_revision must be an integer"),
        ("case_revision", -1, "case_revision must be nonnegative"),
    ],
)
def test_required_extract_fields_are_validated(
    service: InquiryExtractService,
    key: str,
    value,
    message: str,
) -> None:
    context = _base_context(**{key: value})

    with pytest.raises(InquiryExtractValidationError, match=message):
        service.build_inquiry_extract(context)


def test_artifact_type_and_source_kind_are_validated(service: InquiryExtractService) -> None:
    with pytest.raises(InquiryExtractValidationError, match="artifact_type"):
        service.build_inquiry_extract(_base_context(), artifact_type="dispatch")
    with pytest.raises(InquiryExtractValidationError, match="source_kind"):
        service.build_inquiry_extract(_base_context(), source_kind="event_stream")


def test_payload_does_not_include_tenant_or_contact_data(service: InquiryExtractService) -> None:
    payload = service.build_inquiry_extract_payload(
        _base_context(
            tenant_id="tenant-secret",
            contact={"email": "buyer@example.com"},
            user={"name": "Max"},
        )
    )

    assert "tenant_id" not in payload["meta"]
    assert "contact" not in payload
    assert "user" not in payload


def test_validate_manufacturer_view_accepts_service_payload(
    service: InquiryExtractService,
) -> None:
    payload = service.build_inquiry_extract_payload(_base_context())

    result = service.validate_manufacturer_view(payload)

    assert result.valid is True
    assert result.violations == ()
    assert validate_manufacturer_view(payload).valid is True


def test_validate_manufacturer_view_flags_blocked_root_key(
    service: InquiryExtractService,
) -> None:
    result = service.validate_manufacturer_view({"customer_metadata": {"name": "Secret"}})

    assert result.valid is False
    assert result.violations == (
        {"path": "customer_metadata", "reason": "blocked_root_key"},
    )


def test_validate_manufacturer_view_flags_blocked_technical_field(
    service: InquiryExtractService,
) -> None:
    result = service.validate_manufacturer_view(
        {"technical_parameters": {"customer_email": "buyer@example.com"}}
    )

    assert result.valid is False
    assert result.violations == (
        {
            "path": "technical_parameters.customer_email",
            "reason": "blocked_technical_field",
        },
    )


def test_validate_manufacturer_view_flags_blocked_article_reference(
    service: InquiryExtractService,
) -> None:
    result = service.validate_manufacturer_view(
        {
            "article_references": [
                {
                    "reference_type": "customer_internal_article_number",
                    "value": "CUST-123",
                }
            ]
        }
    )

    assert result.valid is False
    assert result.violations == (
        {
            "path": "article_references.0.reference_type",
            "reason": "blocked_article_reference",
        },
    )


def test_service_has_no_langgraph_agent_or_fastapi_imports() -> None:
    source = inspect.getsource(service_module)

    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
