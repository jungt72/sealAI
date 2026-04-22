from __future__ import annotations

import inspect

import pytest

from app.services import anonymization_service as service_module
from app.services.anonymization_service import (
    REDACTED_ADDRESS,
    REDACTED_ARTICLE_NUMBER,
    REDACTED_COMPANY,
    REDACTED_CONTACT,
    REDACTED_EMAIL,
    REDACTED_PERSON,
    REDACTED_PHONE,
    REDACTED_PROJECT_CODE,
    AnonymizationService,
    RedactionAction,
    RedactionCategory,
    anonymize_payload,
    anonymize_text,
    redact_known_sensitive_fields,
    summarize_redactions,
)


@pytest.fixture
def service() -> AnonymizationService:
    return AnonymizationService()


@pytest.mark.parametrize(
    ("field_name", "raw_value", "expected_value", "category"),
    [
        ("email", "alice@example.com", REDACTED_EMAIL, RedactionCategory.EMAIL),
        ("contact_email", "buyer@example.com", REDACTED_EMAIL, RedactionCategory.EMAIL),
        ("customer_email", "kunde@example.de", REDACTED_EMAIL, RedactionCategory.EMAIL),
        ("phone", "+49 221 123456", REDACTED_PHONE, RedactionCategory.PHONE),
        ("contact_phone", "0221 123456", REDACTED_PHONE, RedactionCategory.PHONE),
        ("first_name", "Alice", REDACTED_PERSON, RedactionCategory.PERSON_NAME),
        ("last_name", "Muster", REDACTED_PERSON, RedactionCategory.PERSON_NAME),
        ("person_name", "Alice Muster", REDACTED_PERSON, RedactionCategory.PERSON_NAME),
        ("user_name", "amuster", REDACTED_PERSON, RedactionCategory.PERSON_NAME),
        ("customer_name", "Alice Muster", REDACTED_PERSON, RedactionCategory.PERSON_NAME),
        ("address", "Hauptstrasse 1", REDACTED_ADDRESS, RedactionCategory.ADDRESS),
        ("billing_address", "Hauptstrasse 1", REDACTED_ADDRESS, RedactionCategory.ADDRESS),
        ("contact_identifier", "alice@example.com", REDACTED_CONTACT, RedactionCategory.CONTACT_IDENTIFIER),
        ("project_code", "PRJ-SECRET-42", REDACTED_PROJECT_CODE, RedactionCategory.PROJECT_CODE),
        ("customer_project_code", "K-2026-ABC", REDACTED_PROJECT_CODE, RedactionCategory.PROJECT_CODE),
        ("internal_project_code", "INT-PROJ-7", REDACTED_PROJECT_CODE, RedactionCategory.PROJECT_CODE),
        ("internal_article_number", "INT-4711", REDACTED_ARTICLE_NUMBER, RedactionCategory.CUSTOMER_ARTICLE_NUMBER),
        ("customer_internal_article_number", "CUST-4711", REDACTED_ARTICLE_NUMBER, RedactionCategory.CUSTOMER_ARTICLE_NUMBER),
        ("customer_part_number", "CUST-PART-5", REDACTED_ARTICLE_NUMBER, RedactionCategory.CUSTOMER_ARTICLE_NUMBER),
    ],
)
def test_structured_sensitive_fields_are_replaced(
    service: AnonymizationService,
    field_name: str,
    raw_value: str,
    expected_value: str,
    category: RedactionCategory,
) -> None:
    result = service.anonymize_payload({"technical": "ok", field_name: raw_value})

    assert result.redacted_payload[field_name] == expected_value
    assert result.redacted_payload["technical"] == "ok"
    assert category in result.redaction_categories
    assert result.redaction_count == 1


@pytest.mark.parametrize(
    ("field_name", "category"),
    [
        ("customer_metadata", RedactionCategory.CUSTOMER_METADATA),
        ("customer", RedactionCategory.CUSTOMER_METADATA),
        ("internal_metadata", RedactionCategory.INTERNAL_METADATA),
        ("internal_notes", RedactionCategory.INTERNAL_METADATA),
        ("contact", RedactionCategory.CONTACT_IDENTIFIER),
        ("media", RedactionCategory.MEDIA_METADATA),
        ("photos", RedactionCategory.MEDIA_METADATA),
        ("photo_metadata", RedactionCategory.MEDIA_METADATA),
        ("exif", RedactionCategory.MEDIA_METADATA),
        ("metadata_exif", RedactionCategory.MEDIA_METADATA),
        ("raw_uploads", RedactionCategory.MEDIA_METADATA),
        ("attachments", RedactionCategory.MEDIA_METADATA),
    ],
)
def test_sensitive_containers_are_removed(
    service: AnonymizationService,
    field_name: str,
    category: RedactionCategory,
) -> None:
    result = service.anonymize_payload({"safe": "value", field_name: {"secret": "x"}})

    assert field_name not in result.redacted_payload
    assert result.redacted_payload == {"safe": "value"}
    assert result.events[0].action is RedactionAction.REMOVED
    assert result.events[0].category is category


def test_company_name_is_redacted_only_in_customer_context(service: AnonymizationService) -> None:
    result = service.anonymize_payload(
        {
            "manufacturer": {"company_name": "Neutral Seal Supplier"},
            "customer_details": {"company_name": "Secret Customer GmbH"},
        }
    )

    assert result.redacted_payload["manufacturer"]["company_name"] == "Neutral Seal Supplier"
    assert result.redacted_payload["customer_details"]["company_name"] == REDACTED_COMPANY
    assert RedactionCategory.COMPANY_IDENTIFIER in result.redaction_categories


@pytest.mark.parametrize(
    ("text", "expected", "category"),
    [
        (
            "Bitte Kontakt an alice@example.com senden.",
            f"Bitte Kontakt an {REDACTED_EMAIL} senden.",
            RedactionCategory.EMAIL,
        ),
        (
            "Rueckruf unter +49 221 123456.",
            f"Rueckruf unter {REDACTED_PHONE}.",
            RedactionCategory.PHONE,
        ),
        (
            "Projektcode: PRJ-2026-SECRET muss intern bleiben.",
            f"Projektcode: {REDACTED_PROJECT_CODE} muss intern bleiben.",
            RedactionCategory.PROJECT_CODE,
        ),
        (
            "customer article number CUST-4711 bitte nicht teilen.",
            f"customer article number {REDACTED_ARTICLE_NUMBER} bitte nicht teilen.",
            RedactionCategory.CUSTOMER_ARTICLE_NUMBER,
        ),
        (
            "Kunden Artikel Nr: ABC-123 intern.",
            f"Kunden Artikel Nr: {REDACTED_ARTICLE_NUMBER} intern.",
            RedactionCategory.CUSTOMER_ARTICLE_NUMBER,
        ),
    ],
)
def test_text_redaction_for_narrow_patterns(
    service: AnonymizationService,
    text: str,
    expected: str,
    category: RedactionCategory,
) -> None:
    result = service.anonymize_text(text)

    assert result.redacted_payload == expected
    assert category in result.redaction_categories


def test_text_redacts_multiple_patterns(service: AnonymizationService) -> None:
    result = service.anonymize_text(
        "Projekt: PRJ-77, Kontakt alice@example.com, Tel +49 221 123456."
    )

    assert REDACTED_PROJECT_CODE in result.redacted_payload
    assert REDACTED_EMAIL in result.redacted_payload
    assert REDACTED_PHONE in result.redacted_payload
    assert result.redaction_count == 3


def test_text_does_not_perform_general_name_detection(service: AnonymizationService) -> None:
    result = service.anonymize_text("Max sagt: Welle 42 mm, Druck 3 bar.")

    assert result.redacted_payload == "Max sagt: Welle 42 mm, Druck 3 bar."
    assert result.redaction_count == 0
    assert "does not perform general name recognition" in result.warnings[0]


def test_recursive_dict_and_list_structures_are_redacted(service: AnonymizationService) -> None:
    result = service.anonymize_payload(
        {
            "case": {
                "technical": {"shaft_diameter_mm": 42},
                "contacts": [
                    {"email": "one@example.com"},
                    {"phone": "+49 221 999999"},
                ],
            }
        }
    )

    assert result.redacted_payload["case"]["technical"] == {"shaft_diameter_mm": 42}
    assert result.redacted_payload["case"]["contacts"] == [
        {"email": REDACTED_EMAIL},
        {"phone": REDACTED_PHONE},
    ]
    assert result.redaction_count == 2


def test_tuple_structure_is_preserved(service: AnonymizationService) -> None:
    result = service.anonymize_payload(("alice@example.com", {"phone": "+49 221 123456"}))

    assert result.redacted_payload == (REDACTED_EMAIL, {"phone": REDACTED_PHONE})


@pytest.mark.parametrize(
    "reference",
    [
        {
            "reference_type": "manufacturer_part_number",
            "value": "MFR-42",
            "manufacturer_visible": True,
        },
        {
            "reference_type": "standard_designation",
            "value": "DIN-3760-A-42x62x10",
            "manufacturer_visible": True,
        },
        {
            "reference_type": "public_datasheet_reference",
            "value": "PUBLIC-DS-PTFE",
            "source": "datasheet",
            "manufacturer_visible": True,
        },
    ],
)
def test_public_manufacturer_visible_references_are_preserved(
    service: AnonymizationService,
    reference: dict,
) -> None:
    result = service.anonymize_payload({"article_references": [reference]})

    assert result.redacted_payload == {"article_references": [reference]}
    assert result.redaction_count == 0


def test_customer_internal_reference_is_redacted(service: AnonymizationService) -> None:
    result = service.anonymize_payload(
        {
            "article_references": [
                {
                    "reference_type": "customer_internal_article_number",
                    "value": "CUST-SECRET-9",
                    "manufacturer_visible": True,
                }
            ]
        }
    )

    assert result.redacted_payload["article_references"][0]["value"] == REDACTED_ARTICLE_NUMBER
    assert RedactionCategory.CUSTOMER_ARTICLE_NUMBER in result.redaction_categories


def test_public_reference_not_marked_manufacturer_visible_can_still_redact_nested_email(
    service: AnonymizationService,
) -> None:
    result = service.anonymize_payload(
        {
            "article_references": [
                {
                    "reference_type": "manufacturer_part_number",
                    "value": "MFR-42",
                    "manufacturer_visible": False,
                    "comment": "ask alice@example.com",
                }
            ]
        }
    )

    assert result.redacted_payload["article_references"][0]["value"] == "MFR-42"
    assert result.redacted_payload["article_references"][0]["comment"] == f"ask {REDACTED_EMAIL}"


def test_redact_known_sensitive_fields_alias(service: AnonymizationService) -> None:
    result = service.redact_known_sensitive_fields({"email": "alice@example.com"})
    helper_result = redact_known_sensitive_fields({"email": "alice@example.com"})

    assert result.redacted_payload == {"email": REDACTED_EMAIL}
    assert helper_result.redacted_payload == {"email": REDACTED_EMAIL}


def test_module_level_helpers(service: AnonymizationService) -> None:
    payload_result = anonymize_payload({"phone": "+49 221 123456"})
    text_result = anonymize_text("mail alice@example.com")

    assert payload_result.redacted_payload == {"phone": REDACTED_PHONE}
    assert text_result.redacted_payload == f"mail {REDACTED_EMAIL}"


def test_summary_reports_categories_and_warnings(service: AnonymizationService) -> None:
    result = service.anonymize_payload(
        {
            "email": "alice@example.com",
            "project_code": "PRJ-SECRET",
            "photos": {"exif": "raw"},
        }
    )

    summary = summarize_redactions(result)

    assert summary["redaction_count"] == 3
    assert summary["redaction_categories"] == (
        "email",
        "project_code",
        "media_metadata",
    )
    assert summary["warnings"]


def test_events_include_paths(service: AnonymizationService) -> None:
    result = service.anonymize_payload({"outer": {"contact_email": "alice@example.com"}})

    assert result.events[0].path == "outer.contact_email"
    assert result.events[0].category is RedactionCategory.EMAIL
    assert result.events[0].action is RedactionAction.REPLACED


def test_inquiry_extract_like_payload_remains_stable(service: AnonymizationService) -> None:
    payload = {
        "meta": {"case_id": "case-1", "case_revision": 2},
        "technical_scope": {"request_type": "retrofit", "engineering_path": "rwdr"},
        "technical_parameters": {"shaft_diameter_mm": 42, "medium_name": "water"},
        "privacy_boundary": {"mode": "allowlist"},
    }

    result = service.anonymize_payload(payload)

    assert result.redacted_payload == payload
    assert result.redaction_count == 0


def test_inquiry_extract_like_payload_with_leakage_is_redacted(
    service: AnonymizationService,
) -> None:
    result = service.anonymize_payload(
        {
            "technical_parameters": {
                "shaft_diameter_mm": 42,
                "customer_email": "buyer@example.com",
                "project_code": "PRJ-SECRET",
            }
        }
    )

    assert result.redacted_payload["technical_parameters"]["shaft_diameter_mm"] == 42
    assert result.redacted_payload["technical_parameters"]["customer_email"] == REDACTED_EMAIL
    assert result.redacted_payload["technical_parameters"]["project_code"] == REDACTED_PROJECT_CODE


@pytest.mark.parametrize(
    "safe_payload",
    [
        {"shaft_diameter_mm": 42},
        {"medium_name": "water-glycol"},
        {"pressure_bar": 3.5},
        {"quantity_requested": 4},
        {"norm_results": [{"module_id": "norm_din_3760_iso_6194"}]},
        {"manufacturer": {"display_name": "Neutral Capability Claim"}},
    ],
)
def test_safe_structured_payloads_are_not_changed(
    service: AnonymizationService,
    safe_payload: dict,
) -> None:
    result = service.anonymize_payload(safe_payload)

    assert result.redacted_payload == safe_payload
    assert result.redaction_count == 0


def test_service_has_no_langgraph_agent_or_fastapi_imports() -> None:
    source = inspect.getsource(service_module)

    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
