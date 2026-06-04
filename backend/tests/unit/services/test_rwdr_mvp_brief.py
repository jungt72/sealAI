from __future__ import annotations

import json

import pytest

from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.services.rfq_preview_service import build_rfq_preview_payload
from app.services.rwdr_mvp_brief import (
    ForbiddenLanguageIntelligence,
    RWDR_CASE_STATE_REPOSITORY,
    RWDRCaseStateValidationError,
    RWDR_ALLOWED_STATUSES,
    RWDR_STATUS_COMPLETE,
    RWDR_STATUS_NEEDS_CLARIFICATION,
    RWDR_STATUS_OUT_OF_SCOPE,
    analyze_rwdr_inquiry_text,
    build_rwdr_brief_from_confirmed_fields,
    build_technical_rwdr_rfq_brief,
    create_persisted_rwdr_case,
    export_persisted_rwdr_case_markdown,
    generate_persisted_rwdr_brief,
    get_persisted_rwdr_case,
    update_persisted_rwdr_confirmations,
)


def _case(
    *, engineering_path: str = "rwdr", request_type: str = "rwdr_rfq"
) -> CaseRecord:
    return CaseRecord(
        id="case-rwdr-1",
        case_number="CASE-RWDR-1",
        user_id="user-1",
        tenant_id="tenant-1",
        case_revision=7,
        request_type=request_type,
        engineering_path=engineering_path,
        application_pattern_id="pump",
    )


def _field(
    field_name: str,
    value: object,
    *,
    unit: str | None = None,
    status: str = "user_stated",
    provenance: str = "user_stated",
    confirmation_required: bool = False,
) -> dict[str, object]:
    return {
        "field_name": field_name,
        "value": value,
        "engineering_value": {
            "raw_value": f"{value} {unit}".strip() if unit else str(value),
            "canonical_value": value,
            "unit": unit,
            "quantity_kind": field_name,
        },
        "status": status,
        "provenance": provenance,
        "confidence": "confirmed",
        "confirmation_required": confirmation_required,
    }


def _snapshot(case_fields: dict[str, dict[str, object]]) -> CaseStateSnapshot:
    return CaseStateSnapshot(
        case_id="case-rwdr-1",
        revision=7,
        state_json={"case_state": {"case_fields": case_fields}},
    )


def _complete_rwdr_fields() -> dict[str, dict[str, object]]:
    return {
        "equipment_type": _field("equipment_type", "Pumpe"),
        "seal_function": _field("seal_function", "oil_retention"),
        "medium_name": _field("medium_name", "HLP 46"),
        "temperature_min_c": _field("temperature_min_c", 20, unit="degC"),
        "temperature_max_c": _field("temperature_max_c", 90, unit="degC"),
        "pressure_bar": _field("pressure_bar", 8, unit="bar"),
        "shaft_diameter_mm": _field("shaft_diameter_mm", 40, unit="mm"),
        "housing_bore_diameter_mm": _field("housing_bore_diameter_mm", 62, unit="mm"),
        "seal_width_mm": _field("seal_width_mm", 8, unit="mm"),
        "speed_rpm": _field("speed_rpm", 1450, unit="rpm"),
        "motion_type": _field("motion_type", "rotary"),
        "shaft_condition": _field("shaft_condition", "known_ok"),
        "calculated_speed_m_s": _field(
            "calculated_speed_m_s",
            3.04,
            unit="m/s",
            status="calculated",
            provenance="calculated",
        ),
    }


def test_rfq_preview_embeds_exact_technical_rwdr_rfq_brief_contract() -> None:
    payload = build_rfq_preview_payload(
        case_row=_case(),
        snapshot=_snapshot(_complete_rwdr_fields()),
    )

    brief = payload["rfq_preview"]["technical_rwdr_rfq_brief"]

    assert payload["technical_rwdr_rfq_brief"] == brief
    assert payload["meta"]["technical_rwdr_rfq_brief_status"] == RWDR_STATUS_COMPLETE
    assert brief["artifact_title"] == "Technical RWDR RFQ Brief"
    assert brief["artifact_type"] == "technical_rwdr_rfq_brief"
    assert set(brief["allowed_statuses"]) == set(RWDR_ALLOWED_STATUSES)
    assert brief["status"] == RWDR_STATUS_COMPLETE
    assert brief["evaluation"]["complete_enough_for_manufacturer_evaluation"] is True
    assert brief["no_final_technical_release"] is True
    assert brief["dispatch_enabled"] is False
    assert brief["manufacturer_matching_enabled"] is False
    assert {item["field"] for item in brief["confirmed_case_fields"]} >= {
        "application",
        "inside_medium",
        "temperature_max_c",
        "pressure_differential",
        "shaft_diameter_d1_mm",
        "housing_bore_D_mm",
        "seal_width_b_mm",
        "max_speed_rpm",
        "motion_type",
    }
    assert {item["field"] for item in brief["calculation_fields"]} == {
        "circumferential_speed_mps"
    }


def test_candidate_or_inferred_liability_fields_are_blocked_from_final_brief() -> None:
    fields = _complete_rwdr_fields()
    fields["medium_name"] = _field(
        "medium_name",
        "HLP 46",
        status="candidate",
        provenance="inferred",
        confirmation_required=True,
    )

    payload = build_rfq_preview_payload(case_row=_case(), snapshot=_snapshot(fields))
    brief = payload["technical_rwdr_rfq_brief"]

    assert brief["status"] == RWDR_STATUS_NEEDS_CLARIFICATION
    assert "medium" in brief["canonical_case"]["missing_required_semantics"]
    assert "inside_medium" not in {
        item["field"] for item in brief["confirmed_case_fields"]
    }
    blocked = {
        item["field"]: item["blocked_reason"]
        for item in brief["canonical_case"]["blocked_liability_fields"]
    }
    assert blocked["inside_medium"] == "explicit_user_confirmation_required"


def test_needs_confirmation_liability_field_is_blocked_even_without_flag() -> None:
    fields = _complete_rwdr_fields()
    fields["medium_name"] = _field(
        "medium_name",
        "HLP 46",
        status="needs_confirmation",
        provenance="user_stated",
        confirmation_required=False,
    )

    payload = build_rfq_preview_payload(case_row=_case(), snapshot=_snapshot(fields))
    brief = payload["technical_rwdr_rfq_brief"]

    assert brief["status"] == RWDR_STATUS_NEEDS_CLARIFICATION
    assert brief["evaluation"]["complete_enough_for_manufacturer_evaluation"] is False
    assert "inside_medium" not in {
        item["field"] for item in brief["confirmed_case_fields"]
    }
    blocked = {
        item["field"]: item["blocked_reason"]
        for item in brief["canonical_case"]["blocked_liability_fields"]
    }
    assert blocked["inside_medium"] == "field_status_needs_confirmation"


def test_ambiguous_rwdr_scope_needs_clarification_even_with_complete_fields() -> None:
    payload = build_rfq_preview_payload(
        case_row=_case(engineering_path="", request_type="technical_rfq"),
        snapshot=_snapshot(_complete_rwdr_fields()),
    )
    brief = payload["technical_rwdr_rfq_brief"]

    assert brief["status"] == RWDR_STATUS_NEEDS_CLARIFICATION
    assert brief["canonical_case"]["scope"] == "rwdr_needs_scope_confirmation"
    assert brief["evaluation"]["complete_enough_for_manufacturer_evaluation"] is False
    assert any(
        "RWDR-Bezug ist noch nicht eindeutig bestaetigt" in item
        for item in brief["evaluation"]["open_points"]
    )


def test_non_rwdr_scope_is_out_of_scope_without_matching_or_recommendation() -> None:
    payload = build_rfq_preview_payload(
        case_row=_case(engineering_path="oring"),
        snapshot=_snapshot(_complete_rwdr_fields()),
    )
    brief = payload["technical_rwdr_rfq_brief"]

    assert brief["status"] == RWDR_STATUS_OUT_OF_SCOPE
    assert brief["canonical_case"]["scope"] == "out_of_scope"
    serialized = json.dumps(brief, sort_keys=True).casefold()
    assert "winner" not in serialized
    assert "shortlist" not in serialized
    assert "best manufacturer" not in serialized
    assert "selected manufacturer" not in serialized
    assert "final engineering release" in serialized


def test_direct_brief_builder_uses_only_three_mvp_statuses() -> None:
    brief = build_technical_rwdr_rfq_brief(
        case_row=_case(),
        snapshot=_snapshot(_complete_rwdr_fields()),
        technical_field_envelopes=(
            {
                "field": "medium_name",
                "value": "HLP 46",
                "status": "user_stated",
                "provenance": "user_stated",
                "source_type": "user_stated",
                "validation_status": "user_stated",
                "confirmation_required": False,
            },
        ),
    )

    assert brief["status"] in RWDR_ALLOWED_STATUSES
    assert set(brief["allowed_statuses"]) == {
        RWDR_STATUS_COMPLETE,
        RWDR_STATUS_NEEDS_CLARIFICATION,
        RWDR_STATUS_OUT_OF_SCOPE,
    }


def _rwdr_field(
    field_name: str,
    value: object,
    *,
    unit: str | None = None,
    origin: str = "user_entered",
    source_type: str = "structured_form",
    confirmation_status: str = "confirmed",
    source_span: str | None = None,
) -> dict[str, object]:
    return {
        "field": field_name,
        "value": value,
        "unit": unit,
        "origin": origin,
        "source_type": source_type,
        "status": "confirmed" if confirmation_status == "confirmed" else "candidate",
        "validation_status": "user_stated"
        if confirmation_status == "confirmed"
        else "candidate",
        "confirmation_status": confirmation_status,
        "source_span": source_span,
    }


def _minimal_confirmed_fields() -> list[dict[str, object]]:
    return [
        _rwdr_field("application", "gearbox"),
        _rwdr_field("sealing_function", "oil_retention"),
        _rwdr_field("shaft_diameter_d1_mm", 45, unit="mm"),
        _rwdr_field("housing_bore_D_mm", 62, unit="mm"),
        _rwdr_field("seal_width_b_mm", 8, unit="mm"),
        _rwdr_field("inside_medium", "oil"),
        _rwdr_field("max_speed_rpm", 1500, unit="rpm"),
        _rwdr_field("pressure_differential", 0, unit="bar"),
        _rwdr_field("temperature_min_c", 20, unit="degC"),
        _rwdr_field("temperature_max_c", 80, unit="degC"),
        _rwdr_field("shaft_condition_known", "known_ok"),
    ]


def _brief_for(
    fields: list[dict[str, object]],
    *,
    engineering_path: str = "rwdr",
    request_type: str = "rwdr_rfq",
) -> dict[str, object]:
    return build_technical_rwdr_rfq_brief(
        case_row=_case(engineering_path=engineering_path, request_type=request_type),
        snapshot=_snapshot({}),
        technical_field_envelopes=fields,
    )


def test_minimal_rfq_requires_housing_bore_and_width_before_complete() -> None:
    fields = [
        field
        for field in _minimal_confirmed_fields()
        if field["field"] not in {"housing_bore_D_mm", "seal_width_b_mm"}
    ]

    brief = _brief_for(fields)

    assert brief["status"] == RWDR_STATUS_NEEDS_CLARIFICATION
    assert "housing_bore_D_mm" in brief["canonical_case"]["missing_critical_fields"]
    assert "seal_width_b_mm" in brief["canonical_case"]["missing_critical_fields"]


def test_scope_guard_blocks_hard_out_of_scope_inputs() -> None:
    for text in (
        "Gleitringdichtung für Pumpe gesucht",
        "mechanical face seal required",
        "RWDR für ATEX Bereich",
        "Dichtung für Wasserstoff / hydrogen",
    ):
        fields = _minimal_confirmed_fields() + [_rwdr_field("application", text)]
        brief = _brief_for(fields, engineering_path=text)
        assert brief["status"] == RWDR_STATUS_OUT_OF_SCOPE
        assert brief["evaluation"]["safe_redirect_message"]


def test_evidence_gate_blocks_unconfirmed_llm_extractions_and_explicit_unknown() -> (
    None
):
    fields = _minimal_confirmed_fields()
    fields.append(
        _rwdr_field(
            "material",
            "FKM",
            origin="llm_extracted",
            source_type="user_text",
            confirmation_status="unconfirmed",
            source_span="eventuell FKM",
        )
    )
    fields.append(
        _rwdr_field(
            "old_part_number",
            "ABC",
            origin="llm_extracted",
            source_type="user_text",
            confirmation_status="confirmed",
            source_span=None,
        )
    )
    fields.append(
        _rwdr_field(
            "temperature_max_c",
            None,
            unit="degC",
            origin="llm_extracted",
            source_type="user_text",
            confirmation_status="explicitly_unknown",
        )
    )

    brief = _brief_for(fields)
    confirmed = {item["field"] for item in brief["confirmed_case_fields"]}
    blocked = {
        item["field"]: item["blocked_reason"]
        for item in brief["canonical_case"]["blocked_liability_fields"]
    }

    assert "material" not in confirmed
    assert "old_part_number" not in confirmed
    assert blocked["material"] == "llm_extracted_field_not_user_confirmed"
    assert blocked["old_part_number"] == "llm_extracted_field_missing_source_span"
    assert all(
        item["field"] != "temperature_max_c"
        for item in brief["confirmed_case_fields"]
        if item.get("confirmation_status") == "explicitly_unknown"
    )


def test_unconfirmed_temperature_keeps_status_needs_clarification() -> None:
    fields = [
        field
        for field in _minimal_confirmed_fields()
        if field["field"] != "temperature_max_c"
    ]
    fields.append(
        _rwdr_field(
            "temperature_max_c",
            80,
            unit="degC",
            origin="llm_extracted",
            source_type="user_text",
            confirmation_status="unconfirmed",
            source_span="80 Grad",
        )
    )

    brief = _brief_for(fields)

    assert brief["status"] == RWDR_STATUS_NEEDS_CLARIFICATION
    assert "temperature_max_c" in brief["canonical_case"]["missing_critical_fields"]


def test_circumferential_speed_is_calculated_in_orchestrator() -> None:
    brief = _brief_for(_minimal_confirmed_fields())

    computed = {
        item["field"]: item
        for item in brief["computed_values"]
        if isinstance(item, dict)
    }

    assert brief["status"] == RWDR_STATUS_COMPLETE
    assert computed["circumferential_speed_mps"]["value"] == 3.53


def test_low_pressure_boundary_adds_review_flags() -> None:
    fields = [
        field
        if field["field"] != "pressure_differential"
        else _rwdr_field("pressure_differential", 1, unit="bar")
        for field in _minimal_confirmed_fields()
    ]

    brief = _brief_for(fields)

    flags = set(brief["engineering_review_flags"])
    assert "pressure_design_review_required" in flags
    assert "standard_rwdr_context_warning" in flags
    assert "pressure_stabilized_profile_review_required" in flags
    assert "retaining_ring_or_low_pressure_side_stop_review_required" in flags


def test_measurement_recommendations_cover_missing_and_uncertain_fields() -> None:
    fields = [
        field
        for field in _minimal_confirmed_fields()
        if field["field"] not in {"housing_bore_D_mm"}
    ]
    fields.append(_rwdr_field("max_speed_rpm", 12000, unit="rpm"))

    brief = _brief_for(fields)
    methods = {
        item["field"]: item["method"] for item in brief["measurement_recommendations"]
    }

    assert "housing_bore_D_mm" in methods
    assert "3-point bore gauge" in methods["housing_bore_D_mm"]
    assert "dynamic_runout_DRO" in methods
    assert "shaft_surface_ra" in methods
    assert "shaft_hardness_hrc" in methods


def test_shaft_housing_material_and_leakage_rules_are_review_only() -> None:
    fields = _minimal_confirmed_fields()
    fields.extend(
        [
            _rwdr_field("shaft_condition_known", "eingelaufen"),
            _rwdr_field("shaft_removal_possible", "nein"),
            _rwdr_field("installation_situation", "Montage über Gewinde"),
            _rwdr_field("material", "NBR/FKM/PTFE"),
            _rwdr_field("desired_service_life_or_maintenance_interval", "2 Jahre"),
        ]
    )
    brief = _brief_for(
        fields, engineering_path="RWDR dicht keine Leckage lange Standzeit"
    )

    serialized = json.dumps(brief, ensure_ascii=False).casefold()
    flags = set(brief["engineering_review_flags"])
    assert "shaft_sleeve_review_required" in flags
    assert "split_seal_review_required" in flags
    assert "mounting_damage_risk" in flags
    assert "PTFE_counterface_review_required" in flags
    assert (
        "Welche Leckageanforderung soll der Hersteller bewerten?".casefold()
        in serialized
    )
    assert "fkm empfohlen" not in serialized
    assert "nbr geeignet" not in serialized


def test_brief_contains_required_sections_normative_metadata_and_is_deterministic() -> (
    None
):
    first = _brief_for(_minimal_confirmed_fields())
    second = _brief_for(_minimal_confirmed_fields())

    section_ids = {section["id"] for section in first["sections"]}
    assert section_ids >= {
        "header",
        "status",
        "case_type",
        "user_confirmed_application_category",
        "confirmed_data",
        "unconfirmed_data",
        "missing_critical_fields",
        "missing_helpful_fields",
        "computed_values",
        "engineering_review_flags",
        "recommended_measurement_and_verification_data",
        "manufacturer_questions",
        "regulatory_and_documentation_requirements",
        "leakage_and_service_life_expectations",
        "source_evidence_summary",
        "export_metadata",
        "disclaimer",
    }
    assert (
        first["evaluation"]["computed_values"]
        == second["evaluation"]["computed_values"]
    )
    assert first["evaluation"]["review_flags"] == second["evaluation"]["review_flags"]
    assert (
        first["evaluation"]["manufacturer_questions"]
        == second["evaluation"]["manufacturer_questions"]
    )
    normative_ids = {
        item["reference_id"] for item in first["evaluation"]["normative_references"]
    }
    assert normative_ids >= {
        "ISO_6194_1",
        "ISO_6194_3",
        "ISO_6194_4",
        "ISO_6194_5",
        "ISO_16589",
        "DIN_3760",
    }
    assert all(
        item["does_not_claim_compliance"] is True
        for item in first["evaluation"]["normative_references"]
    )


def test_forbidden_language_guard_allows_only_explicit_negations() -> None:
    guard = ForbiddenLanguageIntelligence()

    assert guard.evaluate_text("FKM empfohlen und approved final solution")
    assert (
        guard.evaluate_text(
            "keine finale technische Eignungsfreigabe, keine Materialfreigabe, keine Produktempfehlung"
        )
        == ()
    )

    brief = _brief_for(_minimal_confirmed_fields())
    serialized = json.dumps(brief, ensure_ascii=False).casefold()
    assert "fkm empfohlen" not in serialized
    assert "recommended material" not in serialized
    assert "recommended product" not in serialized
    assert "approved_solution" not in serialized
    assert "suitable_solution" not in serialized
    assert "final_design" not in serialized


def test_rwdr_confirmation_payload_updates_evidence_and_source_summary() -> None:
    analyzed = analyze_rwdr_inquiry_text(
        "Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min."
    )
    candidates = analyzed["candidate_fields"]
    shaft = next(item for item in candidates if item["field"] == "shaft_diameter_d1_mm")
    shaft["confirmation_status"] = "confirmed"
    shaft["status"] = "confirmed"
    shaft["validation_status"] = "confirmed"

    brief = build_rwdr_brief_from_confirmed_fields(
        raw_inquiry=analyzed["raw_inquiry"],
        fields=(shaft,),
    )

    confirmed = {item["field"]: item for item in brief["confirmed_case_fields"]}
    assert confirmed["shaft_diameter_d1_mm"]["origin"] == "llm_extracted"
    assert confirmed["shaft_diameter_d1_mm"]["source_span"] == "45x62x8"
    source_summary = next(
        section
        for section in brief["sections"]
        if section["id"] == "source_evidence_summary"
    )
    assert source_summary["items"][0]["confirmed_source_spans"] == [
        {
            "field": "shaft_diameter_d1_mm",
            "source_span": "45x62x8",
            "origin": "llm_extracted",
        }
    ]


def test_rwdr_confirmed_input_is_deterministic_and_unknown_not_confirmed() -> None:
    fields = [
        _rwdr_field(
            "inside_medium",
            "Öl",
            origin="llm_extracted",
            source_type="user_text",
            confirmation_status="confirmed",
            source_span="Öl",
        ),
        _rwdr_field(
            "pressure_differential",
            None,
            unit="bar",
            origin="llm_extracted",
            source_type="user_text",
            confirmation_status="explicitly_unknown",
        ),
        _rwdr_field(
            "temperature_max_c",
            "80",
            unit="degC",
            origin="llm_extracted",
            source_type="user_text",
            confirmation_status="unconfirmed",
            source_span="80 °C",
        ),
    ]

    first = build_rwdr_brief_from_confirmed_fields(
        raw_inquiry="RWDR Öl 80 °C", fields=fields
    )
    second = build_rwdr_brief_from_confirmed_fields(
        raw_inquiry="RWDR Öl 80 °C", fields=fields
    )

    confirmed = {item["field"] for item in first["confirmed_case_fields"]}
    assert "inside_medium" in confirmed
    assert "pressure_differential" not in confirmed
    assert "temperature_max_c" not in confirmed
    assert first["status"] == RWDR_STATUS_NEEDS_CLARIFICATION
    assert first["sections"] == second["sections"]


def test_persisted_rwdr_case_stores_raw_inquiry_and_unconfirmed_evidence() -> None:
    state = create_persisted_rwdr_case(
        "Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min."
    )

    assert state["case_id"].startswith("rwdr-")
    assert state["raw_inquiry_text"].startswith("Wellendichtring")
    fields = {item["field"]: item for item in state["evidence_fields"]}
    assert fields["shaft_diameter_d1_mm"]["source_span"] == "45x62x8"
    assert fields["shaft_diameter_d1_mm"]["origin"] == "llm_extracted"
    assert fields["shaft_diameter_d1_mm"]["confirmation_status"] == "unconfirmed"
    assert state["export_metadata"]["manufacturer_matching_enabled"] is False


def test_persisted_rwdr_confirm_edit_unknown_and_reject_decisions() -> None:
    state = create_persisted_rwdr_case("RWDR 45x62x8 Öl 1500 U/min, 80 °C")
    case_id = state["case_id"]

    confirmed = update_persisted_rwdr_confirmations(
        case_id=case_id,
        decisions=[
            {
                "field": "shaft_diameter_d1_mm",
                "action": "confirm",
                "source_span": "45x62x8",
            }
        ],
    )
    shaft = {item["field"]: item for item in confirmed["evidence_fields"]}[
        "shaft_diameter_d1_mm"
    ]
    assert shaft["confirmation_status"] == "confirmed"
    assert shaft["source_span"] == "45x62x8"

    edited = update_persisted_rwdr_confirmations(
        case_id=case_id,
        decisions=[
            {
                "field": "temperature_max_c",
                "action": "edit",
                "value": "85",
                "unit": "degC",
            }
        ],
    )
    temp = {item["field"]: item for item in edited["evidence_fields"]}[
        "temperature_max_c"
    ]
    assert temp["value"] == "85"
    assert temp["previous_value"] == 80
    assert temp["confirmation_status"] == "edited_by_user"

    unknown = update_persisted_rwdr_confirmations(
        case_id=case_id,
        decisions=[{"field": "pressure_differential", "action": "explicitly_unknown"}],
    )
    pressure = {item["field"]: item for item in unknown["evidence_fields"]}[
        "pressure_differential"
    ]
    assert pressure["confirmation_status"] == "explicitly_unknown"
    confirmed_fields = {
        item["field"]
        for item in unknown["technical_rwdr_rfq_brief"]["confirmed_case_fields"]
    }
    assert "pressure_differential" not in confirmed_fields

    rejected = update_persisted_rwdr_confirmations(
        case_id=case_id,
        decisions=[{"field": "inside_medium", "action": "reject"}],
    )
    medium = {item["field"]: item for item in rejected["evidence_fields"]}[
        "inside_medium"
    ]
    assert medium["confirmation_status"] == "rejected"
    confirmed_fields = {
        item["field"]
        for item in rejected["technical_rwdr_rfq_brief"]["confirmed_case_fields"]
    }
    assert "inside_medium" not in confirmed_fields


def test_persisted_rwdr_confirm_without_source_span_for_extracted_liability_is_blocked() -> (
    None
):
    state = create_persisted_rwdr_case("RWDR Öl")
    case_id = state["case_id"]
    stored = RWDR_CASE_STATE_REPOSITORY._cases[case_id]
    injected = dict(stored.evidence_fields[0])
    injected.update(
        {
            "field": "temperature_max_c",
            "value": 80,
            "unit": "degC",
            "origin": "llm_extracted",
            "source_type": "user_text",
            "confirmation_status": "unconfirmed",
            "liability_bearing": True,
        }
    )
    injected.pop("source_span", None)
    RWDR_CASE_STATE_REPOSITORY._cases[case_id] = type(stored)(
        case_id=stored.case_id,
        schema_version=stored.schema_version,
        raw_inquiry_text=stored.raw_inquiry_text,
        extraction_version=stored.extraction_version,
        rule_version=stored.rule_version,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        evidence_fields=(injected,),
        generated_brief=stored.generated_brief,
    )

    # Exercise the public confirmation boundary with a candidate created by a
    # previous extraction pass that has no exact source span.
    with pytest.raises(RWDRCaseStateValidationError):
        update_persisted_rwdr_confirmations(
            case_id=case_id,
            decisions=[{"field": "temperature_max_c", "action": "confirm"}],
        )


def test_persisted_rwdr_brief_and_export_use_confirmed_case_state() -> None:
    state = create_persisted_rwdr_case("Wellendichtring 45x62x8, Öl, 1500 U/min")
    case_id = state["case_id"]
    update_persisted_rwdr_confirmations(
        case_id=case_id,
        decisions=[
            {
                "field": "shaft_diameter_d1_mm",
                "action": "confirm",
                "source_span": "45x62x8",
            },
            {
                "field": "housing_bore_D_mm",
                "action": "confirm",
                "source_span": "45x62x8",
            },
            {"field": "seal_width_b_mm", "action": "confirm", "source_span": "45x62x8"},
            {
                "field": "max_speed_rpm",
                "action": "confirm",
                "source_span": "1500 U/min",
            },
        ],
    )

    brief = generate_persisted_rwdr_brief(case_id)
    computed = {item["field"]: item for item in brief["calculation_fields"]}
    assert computed["circumferential_speed_mps"]["value"] == 3.53

    exported = export_persisted_rwdr_case_markdown(case_id)
    assert exported["case_id"] == case_id
    assert exported["export_format"] == "markdown"
    assert "Technical RWDR RFQ Brief" in exported["content"]
    assert "Umfangsgeschwindigkeit" in exported["content"]
    assert exported["manufacturer_matching_enabled"] is False


def test_persisted_rwdr_deterministic_evaluation_ignores_audit_timestamps() -> None:
    state = create_persisted_rwdr_case("Gleitringdichtung für Pumpe gesucht")
    case_id = state["case_id"]
    first = generate_persisted_rwdr_brief(case_id)
    update_persisted_rwdr_confirmations(
        case_id=case_id,
        decisions=[{"field": "inside_medium", "action": "explicitly_unknown"}],
    )
    second = generate_persisted_rwdr_brief(case_id)

    assert first["status"] == RWDR_STATUS_OUT_OF_SCOPE
    assert second["status"] == RWDR_STATUS_OUT_OF_SCOPE
    assert (
        first["evaluation"]["out_of_scope_reasons"]
        == second["evaluation"]["out_of_scope_reasons"]
    )
