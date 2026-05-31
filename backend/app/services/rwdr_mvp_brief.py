from __future__ import annotations

import math
import re
import uuid
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot

RWDR_MVP_ARTIFACT_TYPE = "technical_rwdr_rfq_brief"
RWDR_MVP_ARTIFACT_TITLE = "Technical RWDR RFQ Brief"
RWDR_MVP_SCHEMA_VERSION = "technical_rwdr_rfq_brief_v1.0.0"
RWDR_CONFIRMATION_SCHEMA_VERSION = "rwdr_confirmation_draft_v1.0.0"
RWDR_CASE_STATE_SCHEMA_VERSION = "rwdr_case_state_v1.0.0"
RWDR_EXTRACTION_VERSION = "rwdr_deterministic_extraction_v1.0.0"
RWDR_RULE_VERSION = "rwdr_rules_v1.0.0"

RWDR_STATUS_COMPLETE = "COMPLETE"
RWDR_STATUS_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
RWDR_STATUS_OUT_OF_SCOPE = "OUT_OF_SCOPE"
RWDR_ALLOWED_STATUSES = frozenset(
    {RWDR_STATUS_COMPLETE, RWDR_STATUS_NEEDS_CLARIFICATION, RWDR_STATUS_OUT_OF_SCOPE}
)

_LIABILITY_BEARING_FIELDS = frozenset(
    {
        "application",
        "application_pattern",
        "application_pattern_id",
        "equipment_type",
        "asset_type",
        "shaft_diameter_d1_mm",
        "housing_bore_D_mm",
        "seal_width_b_mm",
        "housing_bore_diameter_mm",
        "seal_width_mm",
        "medium",
        "medium_name",
        "inside_medium",
        "concentration",
        "temperature_c",
        "temperature_max_c",
        "temperature_min_c",
        "pressure_bar",
        "pressure_at_seal_bar",
        "pressure_differential",
        "shaft_diameter_mm",
        "speed_rpm",
        "max_speed_rpm",
        "calculated_speed_m_s",
        "material",
        "sealing_material_family",
        "standards",
        "old_part_number",
        "old_part_marking",
        "manufacturer_code",
        "hazardous_medium",
        "hazardous_chemical_indication",
        "food_hygiene_requirement",
        "food_contact_required",
        "fda_required",
        "seal_function",
        "sealing_function",
        "seal_family",
        "sealing_type",
        "motion_type",
        "rotation_direction",
        "shaft_condition",
        "shaft_condition_known",
        "leakage_requirement",
        "desired_service_life_h",
    }
)

_CANONICAL_FIELD_ALIASES: dict[str, str] = {
    "application_pattern": "application",
    "application_pattern_id": "application",
    "equipment_type": "application",
    "asset_type": "application",
    "shaft_diameter": "shaft_diameter_d1_mm",
    "shaft_diameter_mm": "shaft_diameter_d1_mm",
    "d1": "shaft_diameter_d1_mm",
    "d1_mm": "shaft_diameter_d1_mm",
    "housing_bore": "housing_bore_D_mm",
    "housing_bore_mm": "housing_bore_D_mm",
    "housing_bore_diameter_mm": "housing_bore_D_mm",
    "D": "housing_bore_D_mm",
    "D_mm": "housing_bore_D_mm",
    "seal_width": "seal_width_b_mm",
    "seal_width_mm": "seal_width_b_mm",
    "width_b_mm": "seal_width_b_mm",
    "b": "seal_width_b_mm",
    "b_mm": "seal_width_b_mm",
    "medium": "inside_medium",
    "medium_name": "inside_medium",
    "inside_or_process_medium": "inside_medium",
    "seal_function": "sealing_function",
    "speed_rpm": "max_speed_rpm",
    "rpm": "max_speed_rpm",
    "pressure_bar": "pressure_differential",
    "pressure_at_seal_bar": "pressure_differential",
    "pressure_differential_bar": "pressure_differential",
    "shaft_condition": "shaft_condition_known",
    "calculated_speed_m_s": "circumferential_speed_mps",
}

_MINIMAL_RWDR_FIELDS: tuple[str, ...] = (
    "sealing_function",
    "shaft_diameter_d1_mm",
    "housing_bore_D_mm",
    "seal_width_b_mm",
    "old_part_marking",
    "old_part_manufacturer",
    "old_part_photo_available",
    "old_part_cross_section_or_drawing_available",
    "existing_design_single_lip",
    "existing_design_dust_lip",
    "existing_design_metal_od",
    "existing_design_rubber_od",
    "existing_design_cassette",
    "existing_design_split",
    "inside_medium",
    "outside_environment_or_contamination",
    "max_speed_rpm",
    "rotation_direction",
    "reversing_operation",
    "pressure_differential",
    "temperature_min_c",
    "temperature_max_c",
    "transient_temperature_c",
    "installation_orientation",
    "installation_situation",
    "shaft_condition_known",
    "shaft_removal_possible",
    "regulatory_or_hygienic_requirements",
    "quantity",
    "target_delivery_date",
    "desired_service_life_or_maintenance_interval",
)

_CRITICAL_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "shaft_diameter_d1_mm": ("shaft_diameter_d1_mm",),
    "housing_bore_D_mm": ("housing_bore_D_mm",),
    "seal_width_b_mm": ("seal_width_b_mm",),
    "sealing_function": ("sealing_function",),
    "inside_medium": ("inside_medium",),
    "max_speed_rpm": ("max_speed_rpm", "explicitly_unknown_speed"),
    "pressure_differential": ("pressure_differential", "explicitly_unknown_pressure"),
    "temperature_min_c": ("temperature_min_c", "explicitly_unknown_temperature"),
    "temperature_max_c": ("temperature_max_c", "explicitly_unknown_temperature"),
    "application": ("application", "explicitly_unknown_application"),
    "shaft_condition_known": (
        "shaft_condition_known",
        "explicitly_unknown_shaft_condition",
    ),
}

_HELPFUL_FIELDS: tuple[str, ...] = tuple(
    field for field in _MINIMAL_RWDR_FIELDS if field not in _CRITICAL_REQUIREMENTS
)

_OUT_OF_SCOPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (reason, re.compile(pattern, re.IGNORECASE))
    for reason, pattern in (
        ("Gleitringdichtungen sind nicht Teil des RWDR-MVP-Scopes.", r"\bgleitringdichtung(en)?\b|\bmechanical\s+face\s+seal\b|\bmechanical\s+seal\b|\bface\s+seal\b"),
        ("Hydraulik-Stangen-/Kolbendichtungen sind nicht Teil des RWDR-MVP-Scopes.", r"hydraulik[-\s]*(stangen|kolben)dichtung|hydraulic\s+(rod|piston)\s+seal"),
        ("O-Ring-Nutberechnung ist nicht Teil des RWDR-MVP-Scopes.", r"o[-\s]?ring[-\s]*nutberechnung|o[-\s]?ring\s+groove\s+design"),
        ("Statische Flachdichtungen als Primärfall sind nicht Teil des RWDR-MVP-Scopes.", r"statische\s+flachdichtung|flange\s+gasket\s+as\s+primary"),
        ("Labyrinthdichtungen als Primärdesign sind nicht Teil des RWDR-MVP-Scopes.", r"labyrinth(dichtung)?"),
        ("ATEX- oder Explosionsschutzfälle sind nicht Teil des RWDR-MVP-Scopes.", r"\batex\b|explosionsgesch[uü]tzt|explosive\s+atmosphere"),
        ("Wasserstoff- und Hochdruckgasfälle sind nicht Teil des RWDR-MVP-Scopes.", r"\bhydrogen\b|\bwasserstoff\b|high[-\s]*pressure\s+gas|hochdruckgas"),
        ("Nuklear-, Luftfahrt- und medizinisch kritische Fälle sind nicht Teil des RWDR-MVP-Scopes.", r"\bnuclear\b|kerntechnik|aerospace|luftfahrt|medical[-\s]*device[-\s]*critical"),
        ("Toxische Prozessmedien sind nicht Teil des RWDR-MVP-Scopes.", r"toxic\s+process\s+media|giftiges\s+prozessmedium"),
        ("Sicherheitskritische Freigabe-, Garantie- oder finale Designentscheidungen sind nicht Teil des RWDR-MVP-Scopes.", r"safety[-\s]*critical\s+approval|life\s+guarantee|final\s+design\s+approval|lebensdauer\s*garantie|finale\s+designfreigabe"),
    )
)

_SAFE_OUT_OF_SCOPE_MESSAGE = (
    "Dieser Fall liegt außerhalb des unterstützten RWDR-MVP-Scopes. "
    "sealing | Intelligence erstellt hierfür keine technische Vorqualifizierung. "
    "Bitte wenden Sie sich direkt an Hersteller, Händler oder eine verantwortliche "
    "technische Stelle."
)

_FORBIDDEN_TERMS: tuple[str, ...] = (
    "freigegeben",
    "freigabe erteilt",
    "geeignet",
    "geeignete dichtung",
    "passend",
    "passende lösung",
    "passende loesung",
    "zertifiziert",
    "sicher geeignet",
    "final empfohlen",
    "empfohlenes material",
    "empfohlenes produkt",
    "approved",
    "certified",
    "safe",
    "suitable",
    "recommended material",
    "recommended product",
    "best manufacturer",
    "final solution",
)

_ALLOWED_FORBIDDEN_DISCLAIMERS: tuple[str, ...] = (
    "keine finale technische eignungsfreigabe",
    "keine materialfreigabe",
    "keine produktempfehlung",
    "keine herstellerfreigabe",
    "no final suitability approval",
    "no material recommendation",
    "no product recommendation",
)

_STANDARD_LOW_PRESSURE_REVIEW_BAR = 0.5

_CONFIRMATION_LIABILITY_FIELDS = frozenset(
    {
        "shaft_diameter_d1_mm",
        "housing_bore_D_mm",
        "seal_width_b_mm",
        "sealing_function",
        "inside_medium",
        "concentration",
        "temperature_min_c",
        "temperature_max_c",
        "transient_temperature_c",
        "pressure_differential",
        "max_speed_rpm",
        "rotation_direction",
        "material",
        "standards",
        "manufacturer_code",
        "old_part_number",
        "hazardous_chemical_indication",
        "food_hygiene_requirement",
        "application",
        "seal_family",
        "sealing_type",
    }
)

_BLOCKING_VALIDATION_STATUSES = frozenset(
    {
        "candidate",
        "conflicting",
        "needs_confirmation",
        "rejected",
        "unvalidated",
        "unknown",
    }
)
_BLOCKING_SOURCE_TYPES = frozenset(
    {"inferred", "llm_research_fallback", "unknown"}
)
_BLOCKING_FIELD_STATUSES = frozenset(
    {
        "candidate",
        "conflict",
        "conflicting",
        "inferred",
        "missing",
        "needs_confirmation",
        "stale",
        "unknown",
    }
)

_SEMANTIC_FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "application": ("application",),
    "medium": ("inside_medium",),
    "temperature": ("temperature_max_c", "temperature_min_c", "explicitly_unknown_temperature"),
    "pressure": ("pressure_differential", "explicitly_unknown_pressure"),
    "shaft_diameter": ("shaft_diameter_d1_mm",),
    "housing_bore": ("housing_bore_D_mm",),
    "seal_width": ("seal_width_b_mm",),
    "sealing_function": ("sealing_function",),
    "speed": ("max_speed_rpm", "circumferential_speed_mps", "explicitly_unknown_speed"),
    "motion": ("motion_type",),
}


@dataclass(frozen=True, slots=True)
class EvidenceField:
    field: str
    value: Any
    unit: str | None
    origin: str
    status: str
    provenance: str
    source_type: str
    validation_status: str
    confirmation_status: str
    evidence_refs: tuple[str, ...]
    source_span: str | None
    liability_bearing: bool
    allowed_in_brief: bool
    blocked_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "field": self.field,
                "value": self.value,
                "unit": self.unit,
                "origin": self.origin,
                "status": self.status,
                "provenance": self.provenance,
                "source_type": self.source_type,
                "validation_status": self.validation_status,
                "confirmation_status": self.confirmation_status,
                "evidence_refs": list(self.evidence_refs),
                "source_span": self.source_span,
                "liability_bearing": self.liability_bearing,
                "allowed_in_brief": self.allowed_in_brief,
                "blocked_reason": self.blocked_reason,
            }
        )


@dataclass(frozen=True, slots=True)
class CanonicalRWDRCase:
    case_id: str
    case_revision: int
    schema_version: str
    case_type: str
    seal_family: str
    user_intent: str
    scope: str
    fields: tuple[EvidenceField, ...]
    canonical_fields: Mapping[str, EvidenceField]
    missing_required_semantics: tuple[str, ...]
    missing_critical_fields: tuple[str, ...]
    missing_helpful_fields: tuple[str, ...]
    blocked_liability_fields: tuple[EvidenceField, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "rwdr-case-v1",
            "case_id": self.case_id,
            "case_revision": self.case_revision,
            "case_type": self.case_type,
            "seal_family": self.seal_family,
            "user_intent": self.user_intent,
            "scope": self.scope,
            "fields": [field.as_dict() for field in self.fields],
            "evidence_fields": {
                key: field.as_dict()
                for key, field in sorted(self.canonical_fields.items())
            },
            "supported_minimal_fields": list(_MINIMAL_RWDR_FIELDS),
            "missing_required_semantics": list(self.missing_required_semantics),
            "missing_critical_fields": list(self.missing_critical_fields),
            "missing_helpful_fields": list(self.missing_helpful_fields),
            "blocked_liability_fields": [
                field.as_dict() for field in self.blocked_liability_fields
            ],
        }


@dataclass(frozen=True, slots=True)
class RWDREvaluation:
    status: str
    complete_enough_for_manufacturer_evaluation: bool
    open_points: tuple[str, ...]
    out_of_scope_reasons: tuple[str, ...]
    safe_redirect_message: str | None = None
    review_flags: tuple[str, ...] = ()
    manufacturer_questions: tuple[str, ...] = ()
    measurement_recommendations: tuple[Mapping[str, Any], ...] = ()
    computed_values: tuple[Mapping[str, Any], ...] = ()
    normative_references: tuple[Mapping[str, Any], ...] = ()
    knowledge_sources: tuple[Mapping[str, Any], ...] = ()
    quality_metrics: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in RWDR_ALLOWED_STATUSES:
            raise ValueError(f"invalid RWDR MVP status: {self.status!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "complete_enough_for_manufacturer_evaluation": (
                self.complete_enough_for_manufacturer_evaluation
            ),
            "open_points": list(self.open_points),
            "out_of_scope_reasons": list(self.out_of_scope_reasons),
            "safe_redirect_message": self.safe_redirect_message,
            "review_flags": list(self.review_flags),
            "manufacturer_questions": list(self.manufacturer_questions),
            "measurement_recommendations": [
                dict(item) for item in self.measurement_recommendations
            ],
            "computed_values": [dict(item) for item in self.computed_values],
            "normative_references": [
                dict(item) for item in self.normative_references
            ],
            "knowledge_sources": [dict(item) for item in self.knowledge_sources],
            "quality_metrics": dict(self.quality_metrics or {}),
        }


@dataclass(frozen=True, slots=True)
class TechnicalRWDRRFQBrief:
    artifact_type: str
    artifact_title: str
    schema_version: str
    case_id: str
    case_revision: int
    status: str
    no_final_technical_release: bool
    dispatch_enabled: bool
    manufacturer_matching_enabled: bool
    canonical_case: CanonicalRWDRCase
    evaluation: RWDREvaluation
    confirmed_case_fields: tuple[EvidenceField, ...]
    calculation_fields: tuple[EvidenceField, ...]
    open_fields: tuple[EvidenceField, ...]

    def as_dict(self) -> dict[str, Any]:
        sections = _brief_sections(
            brief=self,
            canonical_case=self.canonical_case,
            evaluation=self.evaluation,
        )
        return {
            "artifact_type": self.artifact_type,
            "artifact_title": self.artifact_title,
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "case_revision": self.case_revision,
            "status": self.status,
            "allowed_statuses": sorted(RWDR_ALLOWED_STATUSES),
            "no_final_technical_release": self.no_final_technical_release,
            "dispatch_enabled": self.dispatch_enabled,
            "manufacturer_matching_enabled": self.manufacturer_matching_enabled,
            "canonical_case": self.canonical_case.as_dict(),
            "evaluation": self.evaluation.as_dict(),
            "confirmed_case_fields": [
                field.as_dict() for field in self.confirmed_case_fields
            ],
            "calculation_fields": [
                field.as_dict() for field in self.calculation_fields
            ],
            "open_fields": [field.as_dict() for field in self.open_fields],
            "computed_values": [dict(item) for item in self.evaluation.computed_values],
            "engineering_review_flags": list(self.evaluation.review_flags),
            "manufacturer_questions": list(self.evaluation.manufacturer_questions),
            "measurement_recommendations": [
                dict(item) for item in self.evaluation.measurement_recommendations
            ],
            "disclaimer": _RWDR_BRIEF_DISCLAIMER,
            "claim_boundary": {
                "allowed": [
                    "self-declared case facts",
                    "documented facts shown with source references",
                    "deterministic screening calculations",
                    "open points for manufacturer evaluation",
                ],
                "forbidden": [
                    "final engineering release",
                    "product or material recommendation",
                    "manufacturer ranking",
                    "compliance claim",
                    "automatic external dispatch",
                ],
            },
            "sections": sections,
        }


_RWDR_BRIEF_DISCLAIMER = (
    "Dieser Technical RWDR RFQ Brief strukturiert die Anfrage. Er enthält keine "
    "finale technische Eignungsfreigabe, keine Materialfreigabe, keine "
    "Produktempfehlung und keine Herstellerfreigabe. Die finale technische "
    "Bewertung erfolgt durch Hersteller, Händler oder eine verantwortliche "
    "technische Stelle."
)


class EvidenceConfirmationIntelligence:
    """Deterministic gate for liability-bearing RWDR brief facts."""

    def project(self, fields: Sequence[Mapping[str, Any]]) -> tuple[EvidenceField, ...]:
        projected = [self._field_from_envelope(field) for field in fields]
        return tuple(sorted(projected, key=lambda item: item.field))

    def _field_from_envelope(self, field: Mapping[str, Any]) -> EvidenceField:
        raw_name = str(
            field.get("field") or field.get("field_key") or field.get("field_name") or ""
        ).strip()
        name = _canonical_field_name(raw_name)
        engineering_value = _object_mapping(field.get("engineering_value"))
        unit = _optional_text(field.get("unit") or engineering_value.get("unit"))
        source_type = _token(field.get("source_type") or field.get("provenance"))
        validation_status = _token(
            field.get("validation_status") or field.get("status")
        )
        status = _token(field.get("status"))
        provenance = _token(field.get("provenance"))
        origin = _normalize_origin(field, source_type=source_type, provenance=provenance, status=status)
        confirmation_status = _normalize_confirmation_status(field, status=status, validation_status=validation_status)
        evidence_refs = _text_tuple(field.get("evidence_refs"))
        source_span = _source_span(field, engineering_value=engineering_value)
        liability_bearing = name in _LIABILITY_BEARING_FIELDS
        blocked_reason = _blocked_reason(
            field=field,
            liability_bearing=liability_bearing,
            source_type=source_type,
            validation_status=validation_status,
            status=status,
            origin=origin,
            confirmation_status=confirmation_status,
            source_span=source_span,
        )
        return EvidenceField(
            field=name,
            value=field.get("value"),
            unit=unit,
            origin=origin,
            status=status or "unknown",
            provenance=provenance or "missing",
            source_type=source_type or "unknown",
            validation_status=validation_status or "unknown",
            confirmation_status=confirmation_status,
            evidence_refs=evidence_refs,
            source_span=source_span,
            liability_bearing=liability_bearing,
            allowed_in_brief=blocked_reason is None,
            blocked_reason=blocked_reason,
        )


@dataclass(frozen=True, slots=True)
class StoredRWDRCaseState:
    case_id: str
    schema_version: str
    raw_inquiry_text: str
    extraction_version: str
    rule_version: str
    created_at: str
    updated_at: str
    evidence_fields: tuple[Mapping[str, Any], ...]
    generated_brief: Mapping[str, Any] | None = None


class RWDRCaseStateNotFound(KeyError):
    pass


class RWDRCaseStateValidationError(ValueError):
    pass


class RWDRCaseStateRepositoryProtocol(Protocol):
    def create_from_raw_inquiry(self, raw_inquiry: str) -> dict[str, Any]:
        ...

    def get(self, case_id: str) -> dict[str, Any]:
        ...

    def apply_confirmations(
        self,
        *,
        case_id: str,
        decisions: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        ...

    def evaluate(self, case_id: str) -> dict[str, Any]:
        ...

    def generate_brief(self, case_id: str) -> dict[str, Any]:
        ...

    def export_markdown(self, case_id: str) -> dict[str, Any]:
        ...


class RWDRCaseStateRepository:
    """Process-local RWDR case-state repository.

    This keeps the backend as source of truth for the running service without a
    production migration. A durable DB-backed implementation can replace this
    repository behind the same service boundary.
    """

    def __init__(self) -> None:
        self._cases: dict[str, StoredRWDRCaseState] = {}

    def create_from_raw_inquiry(self, raw_inquiry: str) -> dict[str, Any]:
        now = _utc_now()
        case_id = f"rwdr-{uuid.uuid4().hex}"
        candidates = _extract_rwdr_candidate_fields(raw_inquiry)
        state = StoredRWDRCaseState(
            case_id=case_id,
            schema_version=RWDR_CASE_STATE_SCHEMA_VERSION,
            raw_inquiry_text=raw_inquiry,
            extraction_version=RWDR_EXTRACTION_VERSION,
            rule_version=RWDR_RULE_VERSION,
            created_at=now,
            updated_at=now,
            evidence_fields=candidates,
        )
        self._cases[case_id] = self._with_brief(state)
        return self.get(case_id)

    def get(self, case_id: str) -> dict[str, Any]:
        state = self._cases.get(case_id)
        if state is None:
            raise RWDRCaseStateNotFound(case_id)
        return self._as_response(state)

    def apply_confirmations(
        self,
        *,
        case_id: str,
        decisions: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        state = self._require(case_id)
        fields = [dict(item) for item in state.evidence_fields]
        for decision in decisions:
            fields = self._apply_decision(fields, decision)
        updated = StoredRWDRCaseState(
            case_id=state.case_id,
            schema_version=state.schema_version,
            raw_inquiry_text=state.raw_inquiry_text,
            extraction_version=state.extraction_version,
            rule_version=state.rule_version,
            created_at=state.created_at,
            updated_at=_utc_now(),
            evidence_fields=tuple(fields),
        )
        self._cases[case_id] = self._with_brief(updated)
        return self.get(case_id)

    def evaluate(self, case_id: str) -> dict[str, Any]:
        return dict(_object_mapping(self._require(case_id).generated_brief).get("evaluation") or {})

    def generate_brief(self, case_id: str) -> dict[str, Any]:
        state = self._with_brief(self._require(case_id))
        self._cases[case_id] = state
        return dict(state.generated_brief or {})

    def export_markdown(self, case_id: str) -> dict[str, Any]:
        state = self._with_brief(self._require(case_id))
        self._cases[case_id] = state
        brief = dict(state.generated_brief or {})
        return {
            "case_id": case_id,
            "export_format": "markdown",
            "dispatch_enabled": False,
            "manufacturer_matching_enabled": False,
            "content": _brief_markdown(
                brief,
                export_metadata={
                    "case_id": case_id,
                    "revision_number": "-",
                    "export_format": "markdown",
                },
            ),
            "technical_rwdr_rfq_brief": brief,
        }

    def _require(self, case_id: str) -> StoredRWDRCaseState:
        state = self._cases.get(case_id)
        if state is None:
            raise RWDRCaseStateNotFound(case_id)
        return state

    def _with_brief(self, state: StoredRWDRCaseState) -> StoredRWDRCaseState:
        brief = build_rwdr_brief_from_confirmed_fields(
            raw_inquiry=state.raw_inquiry_text,
            fields=state.evidence_fields,
        )
        return StoredRWDRCaseState(
            case_id=state.case_id,
            schema_version=state.schema_version,
            raw_inquiry_text=state.raw_inquiry_text,
            extraction_version=state.extraction_version,
            rule_version=state.rule_version,
            created_at=state.created_at,
            updated_at=state.updated_at,
            evidence_fields=state.evidence_fields,
            generated_brief=brief,
        )

    def _as_response(self, state: StoredRWDRCaseState) -> dict[str, Any]:
        brief = dict(state.generated_brief or {})
        canonical = _object_mapping(brief.get("canonical_case"))
        evaluation = _object_mapping(brief.get("evaluation"))
        return {
            "case_id": state.case_id,
            "schema_version": state.schema_version,
            "raw_inquiry_text": state.raw_inquiry_text,
            "extraction_version": state.extraction_version,
            "rule_version": state.rule_version,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "evidence_fields": [dict(item) for item in state.evidence_fields],
            "evaluation_status": brief.get("status"),
            "missing_critical_fields": list(canonical.get("missing_critical_fields") or ()),
            "missing_helpful_fields": list(canonical.get("missing_helpful_fields") or ()),
            "computed_values": list(evaluation.get("computed_values") or ()),
            "review_flags": list(evaluation.get("review_flags") or ()),
            "manufacturer_questions": list(evaluation.get("manufacturer_questions") or ()),
            "measurement_recommendations": list(evaluation.get("measurement_recommendations") or ()),
            "source_evidence_summary": _section_items(brief, "source_evidence_summary"),
            "technical_rwdr_rfq_brief": brief,
            "export_metadata": {
                "dispatch_enabled": False,
                "manufacturer_matching_enabled": False,
                "markdown_export_endpoint": f"/api/v1/rfq/rwdr/cases/{state.case_id}/export.md",
            },
            "export_markdown": _brief_markdown(brief) if brief else "",
        }

    def _apply_decision(
        self,
        fields: list[dict[str, Any]],
        decision: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        field_name = _canonical_field_name(str(decision.get("field") or ""))
        if not field_name:
            raise RWDRCaseStateValidationError("field is required")
        action = _token(decision.get("action"))
        current_index = next(
            (index for index, item in enumerate(fields) if _canonical_field_name(str(item.get("field") or "")) == field_name),
            None,
        )
        current = dict(fields[current_index]) if current_index is not None else {"field": field_name}
        current["field"] = field_name
        current["user_action_timestamp"] = _utc_now()
        if action == "confirm":
            source_span = _optional_text(decision.get("source_span")) or _optional_text(current.get("source_span"))
            if _token(current.get("origin")) == "llm_extracted" and current.get("liability_bearing") is not False and not source_span:
                raise RWDRCaseStateValidationError("source_span_required_for_confirmed_extracted_liability_field")
            current.update(
                {
                    "confirmation_status": "confirmed",
                    "status": "confirmed",
                    "validation_status": "confirmed",
                    "source_span": source_span,
                }
            )
        elif action == "edit":
            current["previous_value"] = current.get("value")
            current.update(
                {
                    "value": decision.get("value"),
                    "unit": decision.get("unit", current.get("unit")),
                    "origin": "user_entered",
                    "source_type": "structured_form",
                    "confirmation_status": "edited_by_user",
                    "status": "confirmed",
                    "validation_status": "user_stated",
                }
            )
        elif action == "explicitly_unknown":
            current.update(
                {
                    "value": None,
                    "confirmation_status": "explicitly_unknown",
                    "status": "explicitly_unknown",
                    "validation_status": "confirmed",
                }
            )
        elif action == "reject":
            current.update(
                {
                    "confirmation_status": "rejected",
                    "status": "rejected",
                    "validation_status": "rejected",
                }
            )
        else:
            raise RWDRCaseStateValidationError(f"unsupported confirmation action: {action}")
        if current_index is None:
            fields.append(current)
        else:
            fields[current_index] = current
        return fields


class DbRWDRCaseStateRepository:
    """DB-backed RWDR case-state repository using the existing cases payload."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._helper = RWDRCaseStateRepository()

    async def create_from_raw_inquiry(
        self,
        *,
        raw_inquiry: str,
        user_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        now = _utc_now()
        case_id = str(uuid.uuid4())
        state = StoredRWDRCaseState(
            case_id=case_id,
            schema_version=RWDR_CASE_STATE_SCHEMA_VERSION,
            raw_inquiry_text=raw_inquiry,
            extraction_version=RWDR_EXTRACTION_VERSION,
            rule_version=RWDR_RULE_VERSION,
            created_at=now,
            updated_at=now,
            evidence_fields=_extract_rwdr_candidate_fields(raw_inquiry),
        )
        state = self._helper._with_brief(state)
        row = CaseRecord(
            id=case_id,
            case_number=f"RWDR-{case_id[:8].upper()}",
            user_id=user_id,
            tenant_id=tenant_id,
            status="active",
            request_type="rwdr_rfq",
            engineering_path="rwdr",
            schema_version=RWDR_CASE_STATE_SCHEMA_VERSION,
            ruleset_version=RWDR_RULE_VERSION,
            payload=_rwdr_payload_from_state(state),
        )
        self.session.add(row)
        await self._write_snapshot(
            state=state,
            event_type="case_created_after_analyze",
            actor=user_id,
        )
        await self._write_snapshot(
            state=state,
            event_type="extraction_candidates_stored",
            actor=user_id,
        )
        await self.session.commit()
        return await self.get(case_id, tenant_id=tenant_id, user_id=user_id)

    async def get(
        self,
        case_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        return self._row_response(
            await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        )

    async def apply_confirmations(
        self,
        *,
        case_id: str,
        decisions: Sequence[Mapping[str, Any]],
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        row = await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        state = _stored_rwdr_state_from_row(row)
        fields = [dict(item) for item in state.evidence_fields]
        for decision in decisions:
            fields = self._helper._apply_decision(fields, decision)
        updated = StoredRWDRCaseState(
            case_id=state.case_id,
            schema_version=state.schema_version,
            raw_inquiry_text=state.raw_inquiry_text,
            extraction_version=state.extraction_version,
            rule_version=state.rule_version,
            created_at=state.created_at,
            updated_at=_utc_now(),
            evidence_fields=tuple(fields),
        )
        updated = self._helper._with_brief(updated)
        row.payload = _rwdr_payload_from_state(updated)
        row.schema_version = updated.schema_version
        row.ruleset_version = updated.rule_version
        for event_type in _confirmation_event_types(decisions):
            await self._write_snapshot(
                state=updated,
                event_type=event_type,
                actor="user",
            )
        await self.session.commit()
        return await self.get(case_id, tenant_id=tenant_id, user_id=user_id)

    async def evaluate(
        self,
        case_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        row = await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        state = self._helper._with_brief(_stored_rwdr_state_from_row(row))
        row.payload = _rwdr_payload_from_state(state)
        await self._write_snapshot(
            state=state,
            event_type="evaluation_generated",
            actor="system",
        )
        await self.session.commit()
        return dict(_object_mapping(state.generated_brief).get("evaluation") or {})

    async def generate_brief(
        self,
        case_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        row = await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        state = self._helper._with_brief(_stored_rwdr_state_from_row(row))
        row.payload = _rwdr_payload_from_state(state)
        await self._write_snapshot(
            state=state,
            event_type="technical_brief_generated",
            actor="system",
        )
        await self.session.commit()
        return dict(state.generated_brief or {})

    async def export_markdown(
        self,
        case_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        row = await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        state = self._helper._with_brief(_stored_rwdr_state_from_row(row))
        row.payload = _rwdr_payload_from_state(state)
        snapshot = await self._write_snapshot(
            state=state,
            event_type="markdown_export_generated",
            actor="system",
            export_reference={"format": "markdown"},
        )
        await self.session.commit()
        brief = dict(state.generated_brief or {})
        export_metadata = {
            "case_id": case_id,
            "revision_number": snapshot.revision,
            "export_format": "markdown",
        }
        return {
            "case_id": case_id,
            "export_format": "markdown",
            "dispatch_enabled": False,
            "manufacturer_matching_enabled": False,
            "content": _brief_markdown(brief, export_metadata=export_metadata),
            "export_metadata": export_metadata,
            "technical_rwdr_rfq_brief": brief,
        }

    async def export_pdf_document(
        self,
        case_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        exported = await self.export_markdown(
            case_id, tenant_id=tenant_id, user_id=user_id
        )
        brief = dict(exported.get("technical_rwdr_rfq_brief") or {})
        row = await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        snapshot = await self._write_snapshot(
            state=self._helper._with_brief(_stored_rwdr_state_from_row(row)),
            event_type="pdf_export_generated",
            actor="system",
            export_reference={"format": "pdf"},
        )
        await self.session.commit()
        export_metadata = {
            "case_id": case_id,
            "revision_number": snapshot.revision,
            "export_format": "pdf",
        }
        return {
            "export_generated": True,
            "preview_id": case_id,
            "case_id": case_id,
            "case_revision": 0,
            "generated_from_case_revision": 0,
            "artifact_type": RWDR_MVP_ARTIFACT_TYPE,
            "export_format": "pdf",
            "export_metadata": export_metadata,
            "dispatch_enabled": False,
            "automatic_dispatch_allowed": False,
            "no_final_technical_release": True,
            "included_sections": tuple(
                str(section.get("title") or section.get("id") or "")
                for section in _as_mappings(brief.get("sections"))
                if _object_mapping(section)
            ),
            "excluded_sections": (),
            "omitted_disallowed_content": (),
            "content": _rwdr_pdf_content(brief, export_metadata=export_metadata),
            "event_names": (
                "RWDRTechnicalBriefGenerated",
                "RWDRExportGenerated",
                "ExternalDispatchBlocked",
                "RFQDispatchDisabled",
            ),
            "created_at": _utc_now(),
        }

    async def _require(
        self,
        case_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> CaseRecord:
        # Owner-scoped lookup mirrors RfqPreviewService._load_owned_case:
        # a foreign tenant or user gets "not found" with no existence leak.
        result = await self.session.execute(
            select(CaseRecord).where(
                CaseRecord.id == case_id,
                CaseRecord.request_type == "rwdr_rfq",
                CaseRecord.tenant_id == tenant_id,
                CaseRecord.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise RWDRCaseStateNotFound(case_id)
        return row

    def _row_response(self, row: CaseRecord) -> dict[str, Any]:
        return self._helper._as_response(_stored_rwdr_state_from_row(row))

    async def list_snapshots(
        self,
        case_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        snapshots = await self._snapshot_rows(case_id)
        return [_snapshot_summary(row) for row in snapshots]

    async def get_snapshot(
        self,
        case_id: str,
        revision_number: int,
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        for row in await self._snapshot_rows(case_id):
            if int(row.revision) == int(revision_number):
                return _snapshot_detail(row)
        raise RWDRCaseStateNotFound(f"{case_id}:{revision_number}")

    async def diff_snapshots(
        self,
        case_id: str,
        from_revision: int,
        to_revision: int,
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        await self._require(case_id, tenant_id=tenant_id, user_id=user_id)
        from_row: CaseStateSnapshot | None = None
        to_row: CaseStateSnapshot | None = None
        for row in await self._snapshot_rows(case_id):
            if int(row.revision) == int(from_revision):
                from_row = row
            if int(row.revision) == int(to_revision):
                to_row = row
        if from_row is None or to_row is None:
            raise RWDRCaseStateNotFound(f"{case_id}:{from_revision}:{to_revision}")
        return _rwdr_snapshot_diff(from_row, to_row)

    async def _snapshot_rows(self, case_id: str) -> list[CaseStateSnapshot]:
        if hasattr(self.session, "snapshots"):
            return sorted(
                [row for row in getattr(self.session, "snapshots") if row.case_id == case_id],
                key=lambda row: int(row.revision),
            )
        result = await self.session.execute(
            select(CaseStateSnapshot)
            .where(CaseStateSnapshot.case_id == case_id)
            .order_by(CaseStateSnapshot.revision.asc())
        )
        return list(result.scalars().all())

    async def _next_snapshot_revision(self, case_id: str) -> int:
        rows = await self._snapshot_rows(case_id)
        return (max((int(row.revision) for row in rows), default=0) + 1)

    async def _write_snapshot(
        self,
        *,
        state: StoredRWDRCaseState,
        event_type: str,
        actor: str,
        export_reference: Mapping[str, Any] | None = None,
    ) -> CaseStateSnapshot:
        previous_revision = max(
            (int(row.revision) for row in await self._snapshot_rows(state.case_id)),
            default=0,
        )
        revision = previous_revision + 1
        deterministic_payload = _rwdr_deterministic_snapshot_payload(state)
        snapshot_id = str(uuid.uuid4())
        snapshot_payload = {
            "snapshot_id": snapshot_id,
            "case_id": state.case_id,
            "revision_number": revision,
            "previous_revision_number": previous_revision or None,
            "event_type": event_type,
            "schema_version": state.schema_version,
            "rule_version": state.rule_version,
            "extraction_version": state.extraction_version,
            "deterministic_payload_hash": _stable_hash(deterministic_payload),
            "deterministic_payload_json": deterministic_payload,
            "snapshot_payload": _rwdr_payload_from_state(state),
            "created_at": _utc_now(),
            "created_by": actor or "system",
            "export_reference": dict(export_reference or {}),
        }
        snapshot = CaseStateSnapshot(
            id=snapshot_id,
            case_id=state.case_id,
            revision=revision,
            state_json=snapshot_payload,
            basis_hash=snapshot_payload["deterministic_payload_hash"],
            ontology_version=state.schema_version,
            prompt_version=state.extraction_version,
            model_version=state.rule_version,
        )
        self.session.add(snapshot)
        return snapshot


RWDR_CASE_STATE_REPOSITORY = RWDRCaseStateRepository()


@dataclass(frozen=True, slots=True)
class RWDRModuleResult:
    flags: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    missing_critical_fields: tuple[str, ...] = ()
    missing_helpful_fields: tuple[str, ...] = ()
    computed_values: tuple[Mapping[str, Any], ...] = ()
    measurement_recommendations: tuple[Mapping[str, Any], ...] = ()
    out_of_scope_reasons: tuple[str, ...] = ()
    safe_redirect_message: str | None = None
    normative_references: tuple[Mapping[str, Any], ...] = ()
    quality_metrics: Mapping[str, Any] | None = None


class UserIntentIntelligence:
    def evaluate(self, text: str) -> RWDRModuleResult:
        lowered = text.casefold()
        flags = []
        if any(token in lowered for token in ("undicht", "leak", "leckage")):
            flags.append("leakage_failure_intent")
        if any(token in lowered for token in ("rfq", "anfrage", "brief")):
            flags.append("technical_rfq_preparation_intent")
        return RWDRModuleResult(flags=tuple(flags))


class SealTypeIntelligence:
    def evaluate(self, text: str) -> RWDRModuleResult:
        lowered = text.casefold()
        flags = []
        if any(token in lowered for token in ("ptfe", "kassette", "cassette", "split")):
            flags.append("special_rwdr_design_review_required")
        return RWDRModuleResult(flags=tuple(flags))


class ApplicationIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        value = _field_text(fields, "application")
        lowered = value.casefold()
        questions: list[str] = []
        flags: list[str] = []
        if any(token in lowered for token in ("getriebe", "gearbox")):
            questions.extend(
                (
                    "Welches Öl oder Fett wird abgedichtet?",
                    "Ist die Umgebung staubig, nass oder verschmutzt?",
                    "Ist die Wellenlauffläche eingelaufen, beschädigt oder korrodiert?",
                )
            )
            flags.append("oil_additive_material_review_if_oil_unknown")
        elif any(token in lowered for token in ("rührwerk", "ruehrwerk", "mixer", "agitator")):
            questions.extend(
                (
                    "Welches Produktmedium liegt an?",
                    "Welche Reinigungsmedien werden verwendet?",
                    "Liegt Druck oder Vakuum im Behälter an?",
                    "Gibt es Axialspiel, Rundlaufabweichung oder sichtbare Wellenbewegung?",
                )
            )
            flags.extend(
                (
                    "double_side_media_review_required",
                    "shaft_motion_review_required",
                    "cleaning_compatibility_review_required",
                )
            )
        elif any(token in lowered for token in ("pumpe", "pump")):
            questions.extend(
                (
                    "Ist der vorhandene Dichtungstyp ein Radialwellendichtring oder eine Gleitringdichtung?",
                    "Welches Prozessmedium wird gefördert?",
                    "Welcher Druck oder welches Vakuum liegt an?",
                )
            )
            flags.append("mechanical_seal_scope_check_required")
        return RWDRModuleResult(flags=tuple(flags), questions=tuple(questions))


class GeometryDimensionIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        missing = [
            name
            for name in ("shaft_diameter_d1_mm", "housing_bore_D_mm", "seal_width_b_mm")
            if not _field_satisfied(fields, name)
        ]
        flags = []
        d1 = _field_number(fields, "shaft_diameter_d1_mm")
        bore = _field_number(fields, "housing_bore_D_mm")
        width = _field_number(fields, "seal_width_b_mm")
        if d1 is not None and bore is not None and bore <= d1:
            flags.append("dimension_contradiction_housing_not_larger_than_shaft")
        if width is not None and width <= 0:
            flags.append("dimension_contradiction_width_not_positive")
        questions = (
            "Bitte bestätigen Sie die Abmessung als d1 x D x b, z. B. 45 x 62 x 8 mm.",
        ) if missing else ()
        return RWDRModuleResult(
            flags=tuple(flags),
            questions=questions,
            missing_critical_fields=tuple(missing),
        )


class MediumIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        medium = _field_text(fields, "inside_medium").casefold()
        flags: list[str] = []
        questions: list[str] = []
        if any(token in medium for token in ("schokolade", "chocolate")):
            flags.extend(
                (
                    "food_contact_review_required",
                    "cleaning_media_required",
                    "material_compatibility_unresolved",
                    "abrasive_particles_possible",
                )
            )
            questions.extend(
                (
                    "Liegt direkter Produktkontakt vor?",
                    "Welche Reinigungsmedien werden verwendet?",
                    "Welche maximale Produkttemperatur liegt an?",
                    "Enthält das Medium Feststoffe, Zuckerpartikel oder abrasive Bestandteile?",
                )
            )
        if any(token in medium for token in ("chemie", "chemical", "lösungsmittel", "loesungsmittel")):
            flags.append("material_compatibility_unresolved")
        return RWDRModuleResult(flags=tuple(flags), questions=tuple(questions))


class MaterialIntelligence:
    _families = ("NBR", "HNBR", "FKM", "FPM", "ACM", "VMQ", "MVQ", "PTFE", "PEEK", "PPS", "PI")

    def evaluate(self, fields: Mapping[str, EvidenceField], text: str) -> RWDRModuleResult:
        combined = " ".join([text, *(_field_text(fields, key) for key in fields)]).upper()
        flags = []
        questions = []
        for family in self._families:
            if family in combined:
                flags.append(f"material_mention_{family.lower()}_review_required")
        if flags:
            questions.append("Werkstoffprüfung durch Hersteller erforderlich; genanntes Material wurde nicht als Empfehlung übernommen.")
        if "PTFE" in combined:
            flags.extend(("PTFE_counterface_review_required", "PTFE_mounting_review_required"))
            questions.extend(
                (
                    "Ist die Wellenoberfläche und Härte für eine PTFE-/Thermoplast-Lippe bekannt?",
                    "Ist ein Einführkonus oder eine Montagehülse verfügbar?",
                )
            )
        return RWDRModuleResult(flags=tuple(dict.fromkeys(flags)), questions=tuple(dict.fromkeys(questions)))

    def reference_table(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "material_family": family,
                "typical_temperature_context": "generic_reference_only",
                "media_strengths": (),
                "media_limitations": (),
                "dry_run_lubrication_notes": "manufacturer_review_required",
                "counterface_requirements": "manufacturer_review_required",
                "customer_facing_recommendation_forbidden": True,
            }
            for family in (
                "NBR", "HNBR", "FKM/FPM", "ACM", "VMQ/MVQ", "PTFE",
                "PEEK", "PPS", "PI", "spring_steel", "stainless_spring",
                "metal_case", "stainless_case", "OD_coating_acrylic_sealant",
                "unknown",
            )
        )


class OperatingConditionIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        flags: list[str] = []
        questions: list[str] = []
        if not _field_satisfied(fields, "max_speed_rpm") and not _field_satisfied(fields, "explicitly_unknown_speed"):
            questions.append("Welche Drehzahl liegt an der Welle an?")
        if not _field_satisfied(fields, "pressure_differential") and not _field_satisfied(fields, "explicitly_unknown_pressure"):
            questions.append("Ist die Anwendung drucklos oder liegt Differenzdruck an?")
        if _truthy_field(fields, "reversing_operation"):
            flags.append("pumping_direction_or_lip_profile_review_required")
        if _field_satisfied(fields, "pressure_differential") and _field_satisfied(fields, "max_speed_rpm"):
            flags.append("pressure_speed_review_required")
        return RWDRModuleResult(flags=tuple(flags), questions=tuple(questions))


class ShaftCounterfaceIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField], *, speed_class: str = "unknown") -> RWDRModuleResult:
        flags: list[str] = []
        questions: list[str] = []
        shaft_condition = _field_text(fields, "shaft_condition_known").casefold()
        if any(token in shaft_condition for token in ("eingelaufen", "groove", "grooved", "worn", "korrosion", "corroded")):
            flags.append("shaft_sleeve_review_required")
            questions.append("Ist die Wellenlauffläche eingelaufen, beschädigt oder korrodiert?")
        if speed_class in {"high", "extreme"} and not _field_satisfied(fields, "dynamic_runout_DRO"):
            flags.append("dynamic_runout_review_required")
            questions.append("Ist der dynamische Rundlauf der Welle an der Dichtstelle bekannt?")
        if not _field_satisfied(fields, "shaft_surface_ra"):
            flags.append("shaft_surface_review_required")
        return RWDRModuleResult(flags=tuple(flags), questions=tuple(questions))


class HousingInstallationIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        flags: list[str] = []
        questions: list[str] = []
        if _truthy_field(fields, "no_shaft_disassembly_possible") or _field_text(fields, "shaft_removal_possible").casefold() in {"false", "no", "nein"}:
            flags.append("split_seal_review_required")
            questions.append("Kann die Welle für die Montage demontiert werden oder muss eine geteilte Lösung geprüft werden?")
        install = " ".join(
            _field_text(fields, key)
            for key in ("mounting_over_keyway_thread_sharp_edge", "installation_situation")
        ).casefold()
        if any(token in install for token in ("nut", "keyway", "gewinde", "thread", "scharf", "sharp")):
            flags.append("mounting_damage_risk")
            questions.append("Erfolgt die Montage über Nut, Gewinde oder scharfe Kanten?")
        if _field_satisfied(fields, "pressure_differential"):
            flags.append("axial_retention_review_required")
        return RWDRModuleResult(flags=tuple(flags), questions=tuple(questions))


class LubricationIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        text = _field_text(fields, "lubrication_regime").casefold()
        flags = []
        if "grease" in text or "fett" in text:
            flags.append("heat_dissipation_review_required")
        if any(token in text for token in ("dry", "trocken", "poor")):
            flags.append("poor_lubrication_review_required")
        return RWDRModuleResult(flags=tuple(flags))


class EnvironmentContaminationIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField], text: str) -> RWDRModuleResult:
        combined = " ".join([text, _field_text(fields, "outside_environment_or_contamination")]).casefold()
        flags = []
        questions = []
        if any(token in combined for token in ("staub", "dust", "schmutz", "dirt", "sand")):
            flags.append("dust_lip_or_excluder_review_required")
            questions.append("Gibt es Staub, Schmutz oder abrasive Partikel auf der Außenseite der Dichtung?")
        if any(token in combined for token in ("schlamm", "mud", "baumaschine", "construction")):
            flags.extend(("cassette_or_additional_protection_review_required", "shaft_wear_and_lip_wear_review_required"))
        return RWDRModuleResult(flags=tuple(dict.fromkeys(flags)), questions=tuple(questions))


class LipContactMechanicsIntelligence:
    def evaluate(self, flags: Sequence[str]) -> RWDRModuleResult:
        next_flags = []
        flag_set = set(flags)
        if "pressure_speed_review_required" in flag_set:
            next_flags.append("lip_load_review_required")
        if "poor_lubrication_review_required" in flag_set:
            next_flags.append("friction_heat_review_required")
        return RWDRModuleResult(flags=tuple(next_flags))


class FailureModeIntelligence:
    def evaluate(self, text: str) -> RWDRModuleResult:
        lowered = text.casefold()
        flags = []
        if "undicht" in lowered or "leak" in lowered:
            flags.append("failure_leakage_review_required")
        if "hart" in lowered or "hardened" in lowered:
            flags.append("temperature_material_aging_review_required")
        if "spring" in lowered and ("corroded" in lowered or "korrod" in lowered):
            flags.append("spring_material_medium_cleaning_review_required")
        return RWDRModuleResult(flags=tuple(flags))


class RegulatoryComplianceIntelligence:
    def evaluate(self, text: str) -> RWDRModuleResult:
        lowered = text.casefold()
        flags = []
        questions = []
        if any(token in lowered for token in ("fda", "ehEDG".casefold(), "3-a", "1935/2004", "lebensmittel", "food")):
            flags.append("regulatory_requirement_confirmation_required")
            questions.append("Welche Lebensmittel-/Normanforderung soll der Hersteller konkret bewerten?")
        return RWDRModuleResult(flags=tuple(flags), questions=tuple(questions))


class StandardsNomenclatureIntelligence:
    def evaluate(self, text: str) -> RWDRModuleResult:
        lowered = text.casefold()
        flags = []
        if "simmerring" in lowered or "wdr" in lowered or "oil seal" in lowered:
            flags.append("rwdr_generic_term_normalized")
        if "viton" in lowered:
            flags.append("trademark_viton_normalized_to_fkm_mention")
        if "teflon" in lowered:
            flags.append("trademark_teflon_normalized_to_ptfe_mention")
        return RWDRModuleResult(flags=tuple(flags))


class ScopeGuardIntelligence:
    def evaluate(self, text: str) -> RWDRModuleResult:
        reasons: list[str] = []
        for reason, pattern in _OUT_OF_SCOPE_PATTERNS:
            if pattern.search(text):
                reasons.append(reason)
        return RWDRModuleResult(
            out_of_scope_reasons=tuple(dict.fromkeys(reasons)),
            safe_redirect_message=_SAFE_OUT_OF_SCOPE_MESSAGE if reasons else None,
        )


class CalculationIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        d1 = _field_number(fields, "shaft_diameter_d1_mm")
        rpm = _field_number(fields, "max_speed_rpm")
        pressure = _field_number(fields, "pressure_differential")
        temp_max = _field_number(fields, "temperature_max_c")
        computed: list[Mapping[str, Any]] = []
        flags: list[str] = []
        if d1 is not None and rpm is not None:
            speed = math.pi * d1 * rpm / 60000.0
            computed.append(
                {
                    "field": "circumferential_speed_mps",
                    "label": "Umfangsgeschwindigkeit",
                    "value": round(speed, 2),
                    "unit": "m/s",
                    "calculation_type": "exact_kinematic",
                    "formula": "v = pi * d1_mm * rpm / 60000",
                    "input_fields": ("shaft_diameter_d1_mm", "max_speed_rpm"),
                    "not_for_final_technical_release": True,
                }
            )
            speed_class = _speed_class(speed)
        else:
            speed_class = "unknown"
        pressure_class = _pressure_class(pressure)
        temperature_class = _temperature_class(temp_max)
        if pressure is None:
            flags.append("pressure_question_required")
        elif pressure > 0:
            flags.append("pressure_design_review_required")
            flags.append("standard_rwdr_context_warning")
            if pressure > _STANDARD_LOW_PRESSURE_REVIEW_BAR:
                flags.extend(
                    (
                        "pressure_stabilized_profile_review_required",
                        "retaining_ring_or_low_pressure_side_stop_review_required",
                    )
                )
        if pressure is not None and rpm is not None:
            flags.append("pressure_speed_review_required")
        computed.extend(
            (
                {"field": "speed_class", "value": speed_class},
                {"field": "pressure_class", "value": pressure_class},
                {"field": "temperature_class", "value": temperature_class},
                {
                    "field": "advanced_calculations",
                    "hidden": True,
                    "available_functions": (
                        "n_max_from_v_allowed",
                        "mean_lip_contact_pressure",
                        "friction_force",
                        "friction_torque",
                        "friction_power",
                        "heat_flux",
                        "contact_temperature_rise",
                        "thermal_dimensional_change",
                        "metal_OD_press_fit_pressure",
                        "PTFE_PV_check",
                        "Archard_wear_approximation",
                        "wear_limited_life",
                        "leakage_upper_bound_reference",
                    ),
                    "classification": "requires_manufacturer_data",
                    "not_for_final_technical_release": True,
                },
            )
        )
        return RWDRModuleResult(flags=tuple(flags), computed_values=tuple(computed))


class ContradictionIntelligence:
    def evaluate(self, fields: Mapping[str, EvidenceField], flags: Sequence[str]) -> RWDRModuleResult:
        contradiction_flags = tuple(flag for flag in flags if flag.startswith("dimension_contradiction"))
        questions = (
            "Bitte widersprüchliche Abmessungen oder Angaben vor Herstellerbewertung klären.",
        ) if contradiction_flags else ()
        return RWDRModuleResult(flags=contradiction_flags, questions=questions)


class PriorityRiskTriageIntelligence:
    def evaluate(self, missing_critical: Sequence[str], missing_helpful: Sequence[str]) -> RWDRModuleResult:
        flags = [f"critical_missing_{item}" for item in missing_critical]
        flags.extend(f"helpful_missing_{item}" for item in missing_helpful[:8])
        return RWDRModuleResult(flags=tuple(flags))


class QuestionIntelligence:
    _QUESTIONS: dict[str, str] = {
        "shaft_diameter_d1_mm": "Welchen Wellendurchmesser d1 in mm soll der Hersteller bewerten?",
        "housing_bore_D_mm": "Welche Gehäusebohrung D in mm liegt vor?",
        "seal_width_b_mm": "Welche Dichtungsbreite b in mm liegt vor?",
        "sealing_function": "Welche Abdichtaufgabe liegt vor: Öl halten, Schmutz ausschließen oder zwei Medien trennen?",
        "inside_medium": "Welches Medium wird abgedichtet?",
        "max_speed_rpm": "Welche Drehzahl liegt an der Welle an?",
        "pressure_differential": "Ist die Anwendung drucklos oder liegt Differenzdruck an?",
        "temperature_min_c": "Welche minimale Betriebstemperatur tritt an der Dichtstelle auf?",
        "temperature_max_c": "Welche maximale Betriebstemperatur tritt an der Dichtstelle auf?",
        "application": "In welcher Maschine oder Anwendung sitzt der RWDR?",
        "shaft_condition_known": "Ist die Wellenlauffläche eingelaufen, beschädigt oder korrodiert?",
    }

    def evaluate(self, missing_critical: Sequence[str], existing_questions: Sequence[str]) -> RWDRModuleResult:
        questions = [self._QUESTIONS[item] for item in missing_critical if item in self._QUESTIONS]
        questions.extend(existing_questions)
        return RWDRModuleResult(questions=tuple(dict.fromkeys(questions)))


class RFQBriefIntelligence:
    def evaluate(self) -> RWDRModuleResult:
        return RWDRModuleResult()


class KnowledgeSourceIntelligence:
    def evaluate(self) -> RWDRModuleResult:
        return RWDRModuleResult(
            normative_references=(
                {
                    "rule_id": "RWDR-MVP-INTERNAL-RULES-001",
                    "version": "1.0.0",
                    "source_type": "internal_rule",
                    "source_name": "internal MVP rule",
                    "confidence_level": "generic_reference",
                    "manufacturer_specific": False,
                    "valid_from": "2026-05-26",
                },
            )
        )


class DataCaptureLearningIntelligence:
    def evaluate(self) -> RWDRModuleResult:
        return RWDRModuleResult(flags=("learning_capture_structure_prepared",))


class EvaluationQualityIntelligence:
    def evaluate(
        self,
        *,
        fields: Sequence[EvidenceField],
        missing_critical: Sequence[str],
        out_of_scope_reasons: Sequence[str],
        forbidden_violations: Sequence[str],
        measurements: Sequence[Mapping[str, Any]],
    ) -> RWDRModuleResult:
        metrics = {
            "field_extraction_count": len(fields),
            "confirmed_field_count": len([field for field in fields if field.allowed_in_brief and field.confirmation_status != "explicitly_unknown"]),
            "unconfirmed_liability_field_count": len([field for field in fields if field.liability_bearing and not field.allowed_in_brief]),
            "missing_critical_field_count": len(missing_critical),
            "out_of_scope_flag_count": len(out_of_scope_reasons),
            "brief_completeness_score": max(0.0, round(1.0 - (len(missing_critical) / max(1, len(_CRITICAL_REQUIREMENTS))), 2)),
            "measurement_recommendation_count": len(measurements),
            "advanced_calculation_hidden_count": 1,
            "forbidden_language_violation_count": len(forbidden_violations),
        }
        return RWDRModuleResult(quality_metrics=metrics)


class MeasurementVerificationIntelligence:
    _METHODS: dict[str, tuple[str, str]] = {
        "shaft_diameter_d1_mm": ("outside micrometer / Bügelmessschraube", "field_measurable"),
        "housing_bore_D_mm": ("3-point bore gauge / Innenmessgerät", "workshop_measurable"),
        "seal_width_b_mm": ("caliper / Messschieber / Zeichnung", "field_measurable"),
        "dynamic_runout_DRO": ("dial indicator / Messuhr", "workshop_measurable"),
        "static_eccentricity_STBM": ("dial indicator / CMM", "workshop_measurable"),
        "shaft_surface_ra": ("stylus profilometer", "workshop_measurable"),
        "shaft_surface_rz": ("stylus profilometer", "workshop_measurable"),
        "surface_lead_directionality": ("profilometer / optical inspection", "laboratory_or_manufacturer_test"),
        "shaft_hardness_hrc": ("Rockwell C / Vickers for coating", "workshop_measurable"),
        "material": ("FTIR-ATR / DSC/TGA", "laboratory_or_manufacturer_test"),
        "lubricant_aging": ("viscosity, FTIR oil analysis, TAN/TBN", "laboratory_or_manufacturer_test"),
        "particle_contamination": ("particle count, microscopy, ferrography", "laboratory_or_manufacturer_test"),
        "radial_force": ("manufacturer/lab test", "laboratory_or_manufacturer_test"),
        "leakage_friction_temperature": ("test bench", "laboratory_or_manufacturer_test"),
        "PTFE_mounting": ("installation cone / bullet / sleeve check", "workshop_measurable"),
    }

    def evaluate(self, fields: Mapping[str, EvidenceField], missing: Sequence[str], flags: Sequence[str]) -> RWDRModuleResult:
        targets = list(missing)
        if "dynamic_runout_review_required" in flags:
            targets.append("dynamic_runout_DRO")
        if "shaft_surface_review_required" in flags:
            targets.extend(("shaft_surface_ra", "shaft_surface_rz"))
        if "PTFE_mounting_review_required" in flags:
            targets.append("PTFE_mounting")
        targets.extend(("shaft_hardness_hrc",))
        recs = []
        for field in dict.fromkeys(targets):
            if field not in self._METHODS:
                continue
            method, classification = self._METHODS[field]
            recs.append(
                {
                    "field": field,
                    "method": method,
                    "classification": classification,
                }
            )
        return RWDRModuleResult(measurement_recommendations=tuple(recs))


class NormativeReferenceIntelligence:
    def evaluate(self) -> RWDRModuleResult:
        references = (
            ("ISO_6194_1", "ISO 6194-1", "elastomeric radial shaft seals", "types, nominal dimensions, tolerances"),
            ("ISO_6194_3", "ISO 6194-3", "elastomeric radial shaft seals", "storage, handling, installation"),
            ("ISO_6194_4", "ISO 6194-4", "elastomeric radial shaft seals", "performance / qualification tests"),
            ("ISO_6194_5", "ISO 6194-5", "elastomeric radial shaft seals", "visible defects"),
            ("ISO_16589", "ISO 16589 family", "thermoplastic / PTFE radial shaft seals", "reference family"),
            ("DIN_3760", "DIN 3760", "German market reference for standard RWDR", "standard RWDR reference"),
        )
        return RWDRModuleResult(
            normative_references=tuple(
                {
                    "reference_id": ref_id,
                    "name": name,
                    "domain": domain,
                    "mvp_usage": "reference_metadata_only",
                    "notes": notes,
                    "does_not_claim_compliance": True,
                    "does_not_replace_manufacturer_validation": True,
                }
                for ref_id, name, domain, notes in references
            )
        )


class LeakageServiceLifeIntelligence:
    def evaluate(self, text: str, fields: Mapping[str, EvidenceField]) -> RWDRModuleResult:
        lowered = text.casefold()
        questions = []
        if any(token in lowered for token in ("dicht", "keine leckage", "leckagefrei", "no leakage")):
            questions.extend(
                (
                    "Welche Leckageanforderung soll der Hersteller bewerten?",
                    "Ist sichtbare Leckage zulässig?",
                )
            )
        if any(token in lowered for token in ("lange standzeit", "wartungsfrei", "2 jahre", "service life")) or _field_satisfied(fields, "desired_service_life_or_maintenance_interval"):
            questions.extend(
                (
                    "Welche Zielstandzeit oder welches Wartungsintervall wird erwartet?",
                    "Wie lange hielt die bisherige Dichtung?",
                )
            )
        return RWDRModuleResult(questions=tuple(dict.fromkeys(questions)))


class DocumentationRequirementIntelligence:
    def evaluate(self, text: str) -> RWDRModuleResult:
        lowered = text.casefold()
        flags = []
        for token, flag in (
            ("certificate", "certificate_of_conformity_required"),
            ("konform", "certificate_of_conformity_required"),
            ("materialdatenblatt", "material_data_sheet_required"),
            ("fda", "FDA_statement_required"),
            ("1935/2004", "EU_1935_2004_required"),
            ("zeichnung", "drawing_required"),
            ("cad", "CAD_required"),
            ("charge", "batch_traceability_required"),
            ("reach", "REACH_required"),
            ("rohs", "RoHS_required"),
        ):
            if token in lowered:
                flags.append(flag)
        return RWDRModuleResult(flags=tuple(dict.fromkeys(flags)))


class ForbiddenLanguageIntelligence:
    def evaluate_text(self, text: str) -> tuple[str, ...]:
        normalized = text.casefold()
        for allowed in _ALLOWED_FORBIDDEN_DISCLAIMERS:
            normalized = normalized.replace(allowed, "")
        return tuple(term for term in _FORBIDDEN_TERMS if term in normalized)

class RWDRCaseOrchestrator:
    """Build the RWDR MVP brief from the existing RFQ/state boundary."""

    def __init__(self) -> None:
        self._evidence_gate = EvidenceConfirmationIntelligence()
        self._scope_guard = ScopeGuardIntelligence()
        self._calculation = CalculationIntelligence()
        self._measurement = MeasurementVerificationIntelligence()
        self._questions = QuestionIntelligence()
        self._normative = NormativeReferenceIntelligence()
        self._forbidden = ForbiddenLanguageIntelligence()

    def build(
        self,
        *,
        case_row: CaseRecord,
        snapshot: CaseStateSnapshot,
        technical_field_envelopes: Sequence[Mapping[str, Any]],
    ) -> TechnicalRWDRRFQBrief:
        case_revision = int(case_row.case_revision or snapshot.revision or 0)
        evidence_fields = self._evidence_gate.project(technical_field_envelopes)
        canonical_fields = _canonical_field_map(evidence_fields)
        raw_text = _raw_case_text(case_row, snapshot, evidence_fields)
        scope_result = self._scope_guard.evaluate(raw_text)
        scope, scope_reasons = _rwdr_scope(case_row, evidence_fields)
        scope_oos_reasons = scope_reasons if scope == "out_of_scope" else ()
        out_of_scope_reasons = tuple(
            dict.fromkeys((*scope_result.out_of_scope_reasons, *scope_oos_reasons))
        )
        calc_result = self._calculation.evaluate(canonical_fields)
        computed_fields = tuple(_computed_evidence_field(item) for item in calc_result.computed_values if item.get("field") == "circumferential_speed_mps")
        if computed_fields:
            evidence_fields = tuple(sorted((*evidence_fields, *computed_fields), key=lambda item: item.field))
            canonical_fields = _canonical_field_map(evidence_fields)
        module_results = self._run_modules(
            fields=canonical_fields,
            raw_text=raw_text,
            calculation_result=calc_result,
        )
        all_flags = _unique(
            item
            for result in module_results
            for item in result.flags
        )
        missing_semantics = _missing_required_semantics(evidence_fields)
        missing_critical = _missing_critical_fields(canonical_fields)
        missing_helpful = _missing_helpful_fields(canonical_fields)
        blocked_fields = tuple(
            field
            for field in evidence_fields
            if field.liability_bearing and not field.allowed_in_brief
            and not _semantic_group_satisfied_by_other_field(field, evidence_fields)
        )
        open_fields = tuple(
            field
            for field in evidence_fields
            if not field.allowed_in_brief or field.field in missing_semantics
        )
        scope_confirmation_required = scope != "rwdr"
        if out_of_scope_reasons or scope == "out_of_scope":
            status = RWDR_STATUS_OUT_OF_SCOPE
        elif scope_confirmation_required or missing_critical or blocked_fields or _has_contradictions(all_flags):
            status = RWDR_STATUS_NEEDS_CLARIFICATION
        else:
            status = RWDR_STATUS_COMPLETE

        confirmed_fields = tuple(
            field
            for field in evidence_fields
            if field.allowed_in_brief and field.source_type != "deterministic_calculation"
            and field.confirmation_status != "explicitly_unknown"
        )
        calculation_fields = tuple(
            field
            for field in evidence_fields
            if field.allowed_in_brief and field.source_type == "deterministic_calculation"
        )
        canonical_case = CanonicalRWDRCase(
            case_id=str(case_row.id),
            case_revision=case_revision,
            schema_version="rwdr-case-v1",
            case_type=_case_type(raw_text),
            seal_family="radial_shaft_seal",
            user_intent=_user_intent(raw_text),
            scope=scope,
            fields=evidence_fields,
            canonical_fields=canonical_fields,
            missing_required_semantics=missing_semantics,
            missing_critical_fields=missing_critical,
            missing_helpful_fields=missing_helpful,
            blocked_liability_fields=blocked_fields,
        )
        measurement_result = self._measurement.evaluate(
            canonical_fields,
            (*missing_critical, *missing_helpful),
            all_flags,
        )
        question_result = self._questions.evaluate(
            missing_critical,
            tuple(item for result in module_results for item in result.questions),
        )
        forbidden_violations = self._forbidden.evaluate_text(
            " ".join([raw_text, *(question_result.questions), *(all_flags)])
        )
        quality = EvaluationQualityIntelligence().evaluate(
            fields=evidence_fields,
            missing_critical=missing_critical,
            out_of_scope_reasons=out_of_scope_reasons,
            forbidden_violations=forbidden_violations,
            measurements=measurement_result.measurement_recommendations,
        )
        normative_references = tuple(
            dict(item)
            for result in module_results
            for item in result.normative_references
            if item.get("reference_id")
        )
        knowledge_sources = tuple(
            dict(item)
            for result in module_results
            for item in result.normative_references
            if item.get("rule_id")
        )
        evaluation = RWDREvaluation(
            status=status,
            complete_enough_for_manufacturer_evaluation=status
            == RWDR_STATUS_COMPLETE,
            open_points=_open_points(
                (*missing_critical, *missing_semantics),
                blocked_fields,
                scope_reasons=out_of_scope_reasons or scope_reasons
                if scope_confirmation_required and scope != "out_of_scope"
                else (),
            ),
            out_of_scope_reasons=out_of_scope_reasons,
            safe_redirect_message=scope_result.safe_redirect_message if out_of_scope_reasons else None,
            review_flags=all_flags,
            manufacturer_questions=question_result.questions,
            measurement_recommendations=measurement_result.measurement_recommendations,
            computed_values=calc_result.computed_values,
            normative_references=normative_references,
            knowledge_sources=knowledge_sources,
            quality_metrics=quality.quality_metrics,
        )
        return TechnicalRWDRRFQBrief(
            artifact_type=RWDR_MVP_ARTIFACT_TYPE,
            artifact_title=RWDR_MVP_ARTIFACT_TITLE,
            schema_version=RWDR_MVP_SCHEMA_VERSION,
            case_id=str(case_row.id),
            case_revision=case_revision,
            status=status,
            no_final_technical_release=True,
            dispatch_enabled=False,
            manufacturer_matching_enabled=False,
            canonical_case=canonical_case,
            evaluation=evaluation,
            confirmed_case_fields=confirmed_fields,
            calculation_fields=calculation_fields,
            open_fields=open_fields,
        )

    def _run_modules(
        self,
        *,
        fields: Mapping[str, EvidenceField],
        raw_text: str,
        calculation_result: RWDRModuleResult,
    ) -> tuple[RWDRModuleResult, ...]:
        speed_class = "unknown"
        for item in calculation_result.computed_values:
            if item.get("field") == "speed_class":
                speed_class = str(item.get("value") or "unknown")
        first_pass: list[RWDRModuleResult] = [
            UserIntentIntelligence().evaluate(raw_text),
            StandardsNomenclatureIntelligence().evaluate(raw_text),
            SealTypeIntelligence().evaluate(raw_text),
            self._normative.evaluate(),
            GeometryDimensionIntelligence().evaluate(fields),
            ApplicationIntelligence().evaluate(fields),
            MediumIntelligence().evaluate(fields),
            OperatingConditionIntelligence().evaluate(fields),
            calculation_result,
            ShaftCounterfaceIntelligence().evaluate(fields, speed_class=speed_class),
            HousingInstallationIntelligence().evaluate(fields),
            LubricationIntelligence().evaluate(fields),
            EnvironmentContaminationIntelligence().evaluate(fields, raw_text),
            MaterialIntelligence().evaluate(fields, raw_text),
            FailureModeIntelligence().evaluate(raw_text),
            RegulatoryComplianceIntelligence().evaluate(raw_text),
            LeakageServiceLifeIntelligence().evaluate(raw_text, fields),
            DocumentationRequirementIntelligence().evaluate(raw_text),
            KnowledgeSourceIntelligence().evaluate(),
            DataCaptureLearningIntelligence().evaluate(),
        ]
        flags = tuple(flag for result in first_pass for flag in result.flags)
        first_pass.append(LipContactMechanicsIntelligence().evaluate(flags))
        first_pass.append(ContradictionIntelligence().evaluate(fields, flags))
        first_pass.append(
            PriorityRiskTriageIntelligence().evaluate(
                _missing_critical_fields(fields),
                _missing_helpful_fields(fields),
            )
        )
        first_pass.append(RFQBriefIntelligence().evaluate())
        return tuple(first_pass)


def build_technical_rwdr_rfq_brief(
    *,
    case_row: CaseRecord,
    snapshot: CaseStateSnapshot,
    technical_field_envelopes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return RWDRCaseOrchestrator().build(
        case_row=case_row,
        snapshot=snapshot,
        technical_field_envelopes=technical_field_envelopes,
    ).as_dict()


def analyze_rwdr_inquiry_text(raw_inquiry: str) -> dict[str, Any]:
    """Create deterministic RWDR extraction candidates for frontend confirmation."""

    text = str(raw_inquiry or "").strip()
    candidate_fields = _extract_rwdr_candidate_fields(text)
    brief = build_technical_rwdr_rfq_brief(
        case_row=_transient_rwdr_case(),
        snapshot=_transient_rwdr_snapshot(text),
        technical_field_envelopes=candidate_fields,
    )
    return {
        "schema_version": RWDR_CONFIRMATION_SCHEMA_VERSION,
        "raw_inquiry": text,
        "candidate_fields": candidate_fields,
        "technical_rwdr_rfq_brief": brief,
    }


def create_persisted_rwdr_case(raw_inquiry: str) -> dict[str, Any]:
    return RWDR_CASE_STATE_REPOSITORY.create_from_raw_inquiry(str(raw_inquiry or "").strip())


def get_persisted_rwdr_case(case_id: str) -> dict[str, Any]:
    return RWDR_CASE_STATE_REPOSITORY.get(case_id)


def update_persisted_rwdr_confirmations(
    *,
    case_id: str,
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return RWDR_CASE_STATE_REPOSITORY.apply_confirmations(
        case_id=case_id,
        decisions=decisions,
    )


def evaluate_persisted_rwdr_case(case_id: str) -> dict[str, Any]:
    return RWDR_CASE_STATE_REPOSITORY.evaluate(case_id)


def generate_persisted_rwdr_brief(case_id: str) -> dict[str, Any]:
    return RWDR_CASE_STATE_REPOSITORY.generate_brief(case_id)


def export_persisted_rwdr_case_markdown(case_id: str) -> dict[str, Any]:
    return RWDR_CASE_STATE_REPOSITORY.export_markdown(case_id)


async def create_db_persisted_rwdr_case(
    *,
    session: AsyncSession,
    raw_inquiry: str,
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).create_from_raw_inquiry(
        raw_inquiry=str(raw_inquiry or "").strip(),
        user_id=user_id,
        tenant_id=tenant_id,
    )


async def get_db_persisted_rwdr_case(
    *,
    session: AsyncSession,
    case_id: str,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).get(
        case_id, tenant_id=tenant_id, user_id=user_id
    )


async def update_db_persisted_rwdr_confirmations(
    *,
    session: AsyncSession,
    case_id: str,
    decisions: Sequence[Mapping[str, Any]],
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).apply_confirmations(
        case_id=case_id,
        decisions=decisions,
        tenant_id=tenant_id,
        user_id=user_id,
    )


async def evaluate_db_persisted_rwdr_case(
    *,
    session: AsyncSession,
    case_id: str,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).evaluate(
        case_id, tenant_id=tenant_id, user_id=user_id
    )


async def generate_db_persisted_rwdr_brief(
    *,
    session: AsyncSession,
    case_id: str,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).generate_brief(
        case_id, tenant_id=tenant_id, user_id=user_id
    )


async def export_db_persisted_rwdr_case_markdown(
    *,
    session: AsyncSession,
    case_id: str,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).export_markdown(
        case_id, tenant_id=tenant_id, user_id=user_id
    )


async def export_db_persisted_rwdr_case_pdf_document(
    *,
    session: AsyncSession,
    case_id: str,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).export_pdf_document(
        case_id, tenant_id=tenant_id, user_id=user_id
    )


async def list_db_persisted_rwdr_case_snapshots(
    *,
    session: AsyncSession,
    case_id: str,
    tenant_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    return await DbRWDRCaseStateRepository(session).list_snapshots(
        case_id, tenant_id=tenant_id, user_id=user_id
    )


async def get_db_persisted_rwdr_case_snapshot(
    *,
    session: AsyncSession,
    case_id: str,
    revision_number: int,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).get_snapshot(
        case_id, revision_number, tenant_id=tenant_id, user_id=user_id
    )


async def diff_db_persisted_rwdr_case_snapshots(
    *,
    session: AsyncSession,
    case_id: str,
    from_revision: int,
    to_revision: int,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    return await DbRWDRCaseStateRepository(session).diff_snapshots(
        case_id,
        from_revision,
        to_revision,
        tenant_id=tenant_id,
        user_id=user_id,
    )


def build_rwdr_brief_from_confirmed_fields(
    *,
    raw_inquiry: str,
    fields: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return build_technical_rwdr_rfq_brief(
        case_row=_transient_rwdr_case(),
        snapshot=_transient_rwdr_snapshot(raw_inquiry),
        technical_field_envelopes=tuple(fields),
    )


def _extract_rwdr_candidate_fields(raw_inquiry: str) -> tuple[dict[str, Any], ...]:
    text = str(raw_inquiry or "")
    candidates: list[dict[str, Any]] = []
    dimension_match = re.search(
        r"(?P<d1>\d+(?:[.,]\d+)?)\s*(?:x|\*|-)\s*(?P<D>\d+(?:[.,]\d+)?)\s*(?:x|\*|-)\s*(?P<b>\d+(?:[.,]\d+)?)",
        text,
        re.IGNORECASE,
    )
    if dimension_match:
        span = dimension_match.group(0)
        candidates.extend(
            (
                _candidate_field("shaft_diameter_d1_mm", _number_text(dimension_match.group("d1")), "mm", span),
                _candidate_field("housing_bore_D_mm", _number_text(dimension_match.group("D")), "mm", span),
                _candidate_field("seal_width_b_mm", _number_text(dimension_match.group("b")), "mm", span),
            )
        )
    for pattern, field, unit in (
        (r"(?P<span>(?P<value>\d+(?:[.,]\d+)?)\s*(?:u/min|rpm|min-1|1/min))", "max_speed_rpm", "rpm"),
        (r"(?P<span>(?:ca\.?\s*)?(?P<value>-?\d+(?:[.,]\d+)?)\s*(?:°c|grad|degc))", "temperature_max_c", "degC"),
        (r"(?P<span>(?:druck\s*)?(?P<value>\d+(?:[.,]\d+)?)\s*bar)", "pressure_differential", "bar"),
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidates.append(_candidate_field(field, _number_text(match.group("value")), unit, match.group("span")))
    keyword_candidates = (
        ("application", ("getriebe", "gearbox"), "Getriebe"),
        ("application", ("rührwerk", "ruehrwerk", "mixer", "agitator"), "Rührwerk"),
        ("application", ("pumpe", "pump"), "Pumpe"),
        ("inside_medium", ("öl", "oel", "oil"), "Öl"),
        ("inside_medium", ("schokolade", "chocolate"), "Schokolade"),
        ("outside_environment_or_contamination", ("staub", "dust"), "staubige Umgebung"),
        ("sealing_function", ("undicht", "leckage", "leak"), "oil_retention"),
    )
    lowered = text.casefold()
    for field, tokens, value in keyword_candidates:
        if any(token in lowered for token in tokens) and not any(item["field"] == field for item in candidates):
            span = _source_span_for_tokens(text, tokens)
            candidates.append(_candidate_field(field, value, None, span))
    if "rwdr" in lowered or "wellendichtring" in lowered or "radialwellendichtring" in lowered:
        candidates.append(_candidate_field("seal_family", "radial_shaft_seal", None, _source_span_for_tokens(text, ("rwdr", "wellendichtring", "radialwellendichtring"))))
    return tuple(candidates)


def _candidate_field(field: str, value: Any, unit: str | None, source_span: str | None) -> dict[str, Any]:
    return _drop_none(
        {
            "field": field,
            "value": value,
            "unit": unit,
            "origin": "llm_extracted",
            "source_type": "user_text",
            "status": "candidate",
            "validation_status": "candidate",
            "confirmation_status": "unconfirmed",
            "source_span": source_span,
            "liability_bearing": _canonical_field_name(field) in _CONFIRMATION_LIABILITY_FIELDS,
            "confirmation_required": True,
        }
    )


def _brief_markdown(
    brief: Mapping[str, Any],
    *,
    export_metadata: Mapping[str, Any] | None = None,
) -> str:
    if not brief:
        return ""
    canonical = _object_mapping(brief.get("canonical_case"))
    metadata = _object_mapping(export_metadata)
    lines = [
        "# Technical RWDR RFQ Brief",
        "",
        f"Case-ID: {metadata.get('case_id') or canonical.get('case_id') or '-'}",
        f"Revision: {metadata.get('revision_number') or '-'}",
        f"Exportformat: {metadata.get('export_format') or 'markdown'}",
        f"Status: {brief.get('status') or RWDR_STATUS_NEEDS_CLARIFICATION}",
        "",
    ]
    for section in _as_mappings(brief.get("sections")):
        section_id = str(section.get("id") or "")
        if section_id in {"header", "export_metadata"}:
            continue
        title = _rwdr_section_title(section_id, str(section.get("title") or section_id or "Section"))
        lines.append(f"## {title}")
        items = list(section.get("items") or ())
        if not items:
            lines.append("- Keine Angaben gemeldet.")
        else:
            lines.extend(f"- {_markdown_value(item)}" for item in items)
        lines.append("")
    return "\n".join(lines).strip()


def _rwdr_section_title(section_id: str, fallback: str) -> str:
    titles = {
        "status": "Status",
        "case_type": "Anfrageart",
        "user_confirmed_application_category": "Bestätigte Anwendungskategorie",
        "confirmed_data": "Bestätigte Angaben",
        "unconfirmed_data": "Nicht bestätigte Angaben",
        "missing_critical_fields": "Kritisch fehlende Angaben",
        "missing_helpful_fields": "Hilfreich fehlende Angaben",
        "computed_values": "Berechnete Werte",
        "engineering_review_flags": "Engineering Review-Themen",
        "recommended_measurement_and_verification_data": "Empfohlene Mess- und Prüfangaben für Herstellerbewertung",
        "manufacturer_questions": "Herstellerfragen",
        "regulatory_and_documentation_requirements": "Dokumentations-/Regulatorikanforderungen",
        "leakage_and_service_life_expectations": "Leckage- und Standzeiterwartungen",
        "source_evidence_summary": "Quellenübersicht",
        "disclaimer": "Disclaimer",
    }
    return titles.get(section_id, fallback)


def _markdown_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_markdown_value(item)}" for key, item in sorted(value.items()))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return ", ".join(_markdown_value(item) for item in value)
    if value is None:
        return "unknown"
    return str(value)


def _section_items(brief: Mapping[str, Any], section_id: str) -> list[Any]:
    for section in _as_mappings(brief.get("sections")):
        if section.get("id") == section_id:
            return list(section.get("items") or ())
    return []


def _rwdr_payload_from_state(state: StoredRWDRCaseState) -> dict[str, Any]:
    brief = dict(state.generated_brief or {})
    canonical = _object_mapping(brief.get("canonical_case"))
    evaluation = _object_mapping(brief.get("evaluation"))
    markdown = _brief_markdown(brief)
    return {
        "artifact_type": "rwdr_case_state",
        "schema_version": state.schema_version,
        "raw_inquiry_text": state.raw_inquiry_text,
        "extraction_version": state.extraction_version,
        "rule_version": state.rule_version,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "evidence_fields": [dict(item) for item in state.evidence_fields],
        "evaluation_status": brief.get("status"),
        "missing_critical_fields": list(canonical.get("missing_critical_fields") or ()),
        "missing_helpful_fields": list(canonical.get("missing_helpful_fields") or ()),
        "computed_values": list(evaluation.get("computed_values") or ()),
        "review_flags": list(evaluation.get("review_flags") or ()),
        "manufacturer_questions": list(evaluation.get("manufacturer_questions") or ()),
        "measurement_recommendations": list(evaluation.get("measurement_recommendations") or ()),
        "source_evidence_summary": _section_items(brief, "source_evidence_summary"),
        "technical_rwdr_rfq_brief": brief,
        "markdown_export_content": markdown,
        "pdf_export_reference": None,
        "export_metadata": {
            "dispatch_enabled": False,
            "manufacturer_matching_enabled": False,
            "markdown_export_endpoint": f"/api/v1/rfq/rwdr/cases/{state.case_id}/export.md",
            "pdf_export_endpoint": f"/api/v1/rfq/rwdr/cases/{state.case_id}/export.pdf",
        },
    }


def _rwdr_deterministic_snapshot_payload(state: StoredRWDRCaseState) -> dict[str, Any]:
    payload = _rwdr_payload_from_state(state)
    for key in ("created_at", "updated_at"):
        payload.pop(key, None)
    for field in payload.get("evidence_fields") or []:
        if isinstance(field, dict):
            field.pop("user_action_timestamp", None)
    return payload


def _stable_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _confirmation_event_types(decisions: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    events: list[str] = []
    for decision in decisions:
        action = _token(decision.get("action"))
        if action == "edit":
            events.append("evidence_field_edited")
        elif action == "explicitly_unknown":
            events.append("field_marked_explicitly_unknown")
        elif action == "reject":
            events.append("field_rejected")
        elif action == "confirm":
            events.append("confirmation_decision_applied")
    return tuple(events) or ("confirmation_decision_applied",)


def _snapshot_summary(row: CaseStateSnapshot) -> dict[str, Any]:
    state = _object_mapping(row.state_json)
    return {
        "snapshot_id": row.id,
        "case_id": row.case_id,
        "revision_number": row.revision,
        "event_type": state.get("event_type"),
        "created_at": row.created_at,
        "schema_version": state.get("schema_version"),
        "rule_version": state.get("rule_version"),
        "extraction_version": state.get("extraction_version"),
        "deterministic_payload_hash": row.basis_hash or state.get("deterministic_payload_hash"),
        "previous_revision_number": state.get("previous_revision_number"),
        "export_reference": state.get("export_reference") or {},
    }


def _snapshot_detail(row: CaseStateSnapshot) -> dict[str, Any]:
    detail = _snapshot_summary(row)
    detail["snapshot_payload"] = _object_mapping(row.state_json).get("snapshot_payload") or {}
    detail["deterministic_payload_json"] = _object_mapping(row.state_json).get("deterministic_payload_json") or {}
    return detail


def _rwdr_snapshot_diff(from_row: CaseStateSnapshot, to_row: CaseStateSnapshot) -> dict[str, Any]:
    from_state = _object_mapping(from_row.state_json)
    to_state = _object_mapping(to_row.state_json)
    from_payload = _deterministic_snapshot_payload_from_row(from_row)
    to_payload = _deterministic_snapshot_payload_from_row(to_row)
    same_revision = int(from_row.revision) == int(to_row.revision)

    status_from = _payload_status(from_payload)
    status_to = _payload_status(to_payload)
    evidence_field_diffs = [] if same_revision else _evidence_field_diffs(
        from_payload.get("evidence_fields"),
        to_payload.get("evidence_fields"),
    )
    missing_critical_diff = _list_diff(
        from_payload.get("missing_critical_fields"),
        to_payload.get("missing_critical_fields"),
    )
    missing_helpful_diff = _list_diff(
        from_payload.get("missing_helpful_fields"),
        to_payload.get("missing_helpful_fields"),
    )
    computed_values_diff = _keyed_list_diff(
        from_payload.get("computed_values"),
        to_payload.get("computed_values"),
    )
    review_flags_diff = _keyed_list_diff(
        from_payload.get("review_flags"),
        to_payload.get("review_flags"),
    )
    manufacturer_questions_diff = _keyed_list_diff(
        from_payload.get("manufacturer_questions"),
        to_payload.get("manufacturer_questions"),
    )
    measurement_recommendations_diff = _keyed_list_diff(
        from_payload.get("measurement_recommendations"),
        to_payload.get("measurement_recommendations"),
    )
    source_evidence_summary_diff = _keyed_list_diff(
        from_payload.get("source_evidence_summary"),
        to_payload.get("source_evidence_summary"),
    )
    brief_diff = _brief_diff(
        from_payload.get("technical_rwdr_rfq_brief"),
        to_payload.get("technical_rwdr_rfq_brief"),
    )
    export_diff = _export_diff(from_state, to_state, from_payload, to_payload)

    if same_revision:
        missing_critical_diff = _empty_list_diff(from_payload.get("missing_critical_fields"))
        missing_helpful_diff = _empty_list_diff(from_payload.get("missing_helpful_fields"))
        computed_values_diff = _empty_keyed_diff()
        review_flags_diff = _empty_keyed_diff()
        manufacturer_questions_diff = _empty_keyed_diff()
        measurement_recommendations_diff = _empty_keyed_diff()
        source_evidence_summary_diff = _empty_keyed_diff()
        brief_diff = _brief_diff(from_payload.get("technical_rwdr_rfq_brief"), from_payload.get("technical_rwdr_rfq_brief"))
        export_diff = _export_diff(from_state, from_state, from_payload, from_payload)

    return {
        "case_id": from_row.case_id,
        "from_revision": int(from_row.revision),
        "to_revision": int(to_row.revision),
        "from_event_type": from_state.get("event_type"),
        "to_event_type": to_state.get("event_type"),
        "summary": {
            "changed_fields_count": len(evidence_field_diffs),
            "added_missing_fields_count": len(missing_critical_diff["added"]) + len(missing_helpful_diff["added"]),
            "removed_missing_fields_count": len(missing_critical_diff["removed"]) + len(missing_helpful_diff["removed"]),
            "status_changed": (status_from != status_to) if not same_revision else False,
            "brief_changed": bool(brief_diff.get("section_changes")) if not same_revision else False,
            "export_changed": bool(export_diff.get("markdown_export_changed") or export_diff.get("pdf_export_changed")) if not same_revision else False,
        },
        "status_diff": {"from": status_from, "to": status_to} if status_from != status_to and not same_revision else {},
        "evidence_field_diffs": evidence_field_diffs,
        "missing_critical_fields_diff": missing_critical_diff,
        "missing_helpful_fields_diff": missing_helpful_diff,
        "computed_values_diff": computed_values_diff,
        "review_flags_diff": review_flags_diff,
        "manufacturer_questions_diff": manufacturer_questions_diff,
        "measurement_recommendations_diff": measurement_recommendations_diff,
        "source_evidence_summary_diff": source_evidence_summary_diff,
        "brief_diff": brief_diff,
        "export_diff": export_diff,
        "audit_metadata": {
            "from_created_at": from_state.get("created_at") or from_row.created_at,
            "to_created_at": to_state.get("created_at") or to_row.created_at,
            "audit_metadata_excluded_from_deterministic_diff": True,
        },
    }


def _deterministic_snapshot_payload_from_row(row: CaseStateSnapshot) -> dict[str, Any]:
    state = _object_mapping(row.state_json)
    deterministic = _object_mapping(state.get("deterministic_payload_json"))
    if deterministic:
        return _strip_audit_metadata(deterministic)
    return _strip_audit_metadata(_object_mapping(state.get("snapshot_payload")))


def _strip_audit_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_audit_metadata(item)
            for key, item in value.items()
            if str(key) not in {"created_at", "updated_at", "trace_id", "request_id", "user_action_timestamp"}
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_strip_audit_metadata(item) for item in value]
    return value


def _payload_status(payload: Mapping[str, Any]) -> str | None:
    return _optional_text(payload.get("evaluation_status")) or _optional_text(
        _object_mapping(payload.get("technical_rwdr_rfq_brief")).get("status")
    )


def _evidence_field_diffs(from_fields: Any, to_fields: Any) -> list[dict[str, Any]]:
    from_by_field = {
        str(item.get("field")): _field_diff_view(item)
        for item in _as_mappings(from_fields)
        if item.get("field")
    }
    to_by_field = {
        str(item.get("field")): _field_diff_view(item)
        for item in _as_mappings(to_fields)
        if item.get("field")
    }
    diffs: list[dict[str, Any]] = []
    for field in sorted(set(from_by_field) | set(to_by_field)):
        left = from_by_field.get(field)
        right = to_by_field.get(field)
        if left == right:
            continue
        if left is None:
            change_type = "added"
        elif right is None:
            change_type = "removed"
        elif left.get("confirmation_status") != right.get("confirmation_status"):
            change_type = "confirmation_status_changed"
        elif left.get("value") != right.get("value"):
            change_type = "value_changed"
        elif left.get("source_span") != right.get("source_span"):
            change_type = "source_span_changed"
        elif left.get("allowed_in_brief") != right.get("allowed_in_brief"):
            change_type = "allowed_in_brief_changed"
        elif left.get("liability_bearing") != right.get("liability_bearing"):
            change_type = "liability_bearing_changed"
        else:
            change_type = "changed"
        diffs.append(
            {
                "field": field,
                "change_type": change_type,
                "from": left or {},
                "to": right or {},
                "source_span_changed": bool((left or {}).get("source_span") != (right or {}).get("source_span")),
            }
        )
    return diffs


def _field_diff_view(field: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "value",
        "unit",
        "origin",
        "source_type",
        "source_span",
        "confirmation_status",
        "liability_bearing",
        "allowed_in_brief",
        "previous_value",
    )
    return {key: field.get(key) for key in keys if key in field}


def _list_diff(from_items: Any, to_items: Any) -> dict[str, list[str]]:
    left = {str(item) for item in (from_items or [])}
    right = {str(item) for item in (to_items or [])}
    return {
        "added": sorted(right - left),
        "removed": sorted(left - right),
        "unchanged": sorted(left & right),
    }


def _empty_list_diff(items: Any) -> dict[str, list[str]]:
    return {"added": [], "removed": [], "unchanged": sorted(str(item) for item in (items or []))}


def _keyed_list_diff(from_items: Any, to_items: Any) -> dict[str, list[Any]]:
    left = {_diff_item_key(item): item for item in _sequence_items(from_items)}
    right = {_diff_item_key(item): item for item in _sequence_items(to_items)}
    added = [right[key] for key in sorted(set(right) - set(left))]
    removed = [left[key] for key in sorted(set(left) - set(right))]
    changed = [
        {"from": left[key], "to": right[key]}
        for key in sorted(set(left) & set(right))
        if _stable_json(left[key]) != _stable_json(right[key])
    ]
    return {"added": added, "changed": changed, "removed": removed}


def _empty_keyed_diff() -> dict[str, list[Any]]:
    return {"added": [], "changed": [], "removed": []}


def _sequence_items(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _diff_item_key(item: Any) -> str:
    if isinstance(item, Mapping):
        for key in ("field", "id", "code", "question", "flag", "method", "reference_id"):
            if item.get(key):
                return f"{key}:{item.get(key)}"
    return _stable_json(item)


def _brief_diff(from_brief: Any, to_brief: Any) -> dict[str, Any]:
    left = _object_mapping(from_brief)
    right = _object_mapping(to_brief)
    left_sections = _sections_by_id(left)
    right_sections = _sections_by_id(right)
    changes: list[dict[str, Any]] = []
    for section_id in sorted(set(left_sections) | set(right_sections)):
        if section_id not in left_sections:
            changes.append({"section_id": section_id, "change_type": "section_added"})
        elif section_id not in right_sections:
            changes.append({"section_id": section_id, "change_type": "section_removed"})
        elif _stable_json(left_sections[section_id]) != _stable_json(right_sections[section_id]):
            changes.append({"section_id": section_id, "change_type": "section_changed"})
    return {
        "brief_present_from": bool(left),
        "brief_present_to": bool(right),
        "section_changes": changes,
    }


def _sections_by_id(brief: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    for index, section in enumerate(_as_mappings(brief.get("sections"))):
        section_id = str(section.get("id") or section.get("title") or f"section_{index}")
        sections[section_id] = {
            "id": section.get("id"),
            "title": section.get("title"),
            "item_count": len(list(section.get("items") or ())),
            "items_hash": _stable_json(section.get("items") or []),
        }
    return sections


def _export_diff(
    from_state: Mapping[str, Any],
    to_state: Mapping[str, Any],
    from_payload: Mapping[str, Any],
    to_payload: Mapping[str, Any],
) -> dict[str, Any]:
    from_export = _object_mapping(from_state.get("export_reference"))
    to_export = _object_mapping(to_state.get("export_reference"))
    from_format = _optional_text(from_export.get("format"))
    to_format = _optional_text(to_export.get("format"))
    return {
        "markdown_export_changed": from_format != to_format and "markdown" in {from_format, to_format},
        "pdf_export_changed": from_format != to_format and "pdf" in {from_format, to_format},
        "from_export_reference": from_export,
        "to_export_reference": to_export,
        "export_metadata_changed": _stable_json(from_payload.get("export_metadata")) != _stable_json(to_payload.get("export_metadata")),
    }


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _stored_rwdr_state_from_row(row: CaseRecord) -> StoredRWDRCaseState:
    payload = _object_mapping(row.payload)
    created_at = _optional_text(payload.get("created_at")) or (
        row.created_at.isoformat() if row.created_at else _utc_now()
    )
    updated_at = _optional_text(payload.get("updated_at")) or (
        row.updated_at.isoformat() if row.updated_at else created_at
    )
    return StoredRWDRCaseState(
        case_id=str(row.id),
        schema_version=_optional_text(payload.get("schema_version")) or RWDR_CASE_STATE_SCHEMA_VERSION,
        raw_inquiry_text=_optional_text(payload.get("raw_inquiry_text")) or "",
        extraction_version=_optional_text(payload.get("extraction_version")) or RWDR_EXTRACTION_VERSION,
        rule_version=_optional_text(payload.get("rule_version")) or RWDR_RULE_VERSION,
        created_at=created_at,
        updated_at=updated_at,
        evidence_fields=tuple(_as_mappings(payload.get("evidence_fields"))),
        generated_brief=_object_mapping(payload.get("technical_rwdr_rfq_brief")),
    )


def _rwdr_pdf_content(
    brief: Mapping[str, Any],
    *,
    export_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    sections = tuple(_as_mappings(brief.get("sections")))
    metadata = _object_mapping(export_metadata)
    return {
        "title": RWDR_MVP_ARTIFACT_TITLE,
        "safe_case_reference": {
            "case_id": metadata.get("case_id") or _object_mapping(brief.get("canonical_case")).get("case_id") or "rwdr",
        },
        "revision": {"case_revision": metadata.get("revision_number") or 0},
        "technical_fields": list(brief.get("confirmed_case_fields") or ()),
        "manufacturer_review_notes": list(
            _object_mapping(brief.get("evaluation")).get("manufacturer_questions") or ()
        ),
        "technical_rwdr_rfq_brief": dict(brief),
        "rwdr_sections": [
            {
                "title": _rwdr_section_title(
                    str(section.get("id") or ""),
                    str(section.get("title") or section.get("id") or ""),
                ),
                "items": list(section.get("items") or ()),
            }
            for section in sections
            if section.get("id") not in {"header"}
        ],
    }


def _as_mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number_text(value: str) -> float:
    return float(str(value).replace(",", "."))


def _source_span_for_tokens(text: str, tokens: Sequence[str]) -> str | None:
    lowered = text.casefold()
    for token in tokens:
        index = lowered.find(token.casefold())
        if index >= 0:
            return text[index : index + len(token)]
    return None


def _transient_rwdr_case() -> CaseRecord:
    return CaseRecord(
        id="rwdr-confirmation-draft",
        case_number="RWDR-CONFIRMATION-DRAFT",
        user_id="local-user",
        tenant_id="local-tenant",
        case_revision=0,
        request_type="rwdr_rfq",
        engineering_path="rwdr",
        application_pattern_id=None,
    )


def _transient_rwdr_snapshot(raw_inquiry: str) -> CaseStateSnapshot:
    return CaseStateSnapshot(
        case_id="rwdr-confirmation-draft",
        revision=0,
        state_json={"raw_inquiry": raw_inquiry, "case_state": {"raw_inquiry": raw_inquiry}},
    )


def _canonical_field_name(name: str) -> str:
    token = str(name or "").strip()
    return _CANONICAL_FIELD_ALIASES.get(token, token)


def _canonical_field_map(fields: Sequence[EvidenceField]) -> dict[str, EvidenceField]:
    result: dict[str, EvidenceField] = {}
    for field in fields:
        if field.field not in result:
            result[field.field] = field
            continue
        current = result[field.field]
        if field.allowed_in_brief and (
            not current.allowed_in_brief
            or field.value not in (None, "")
            or field.confirmation_status == "explicitly_unknown"
        ):
            result[field.field] = field
    return result


def _normalize_origin(
    field: Mapping[str, Any],
    *,
    source_type: str,
    provenance: str,
    status: str,
) -> str:
    raw = _token(field.get("origin"))
    if raw in {"user_entered", "llm_extracted", "deterministic_calculation", "inferred"}:
        return raw
    combined = " ".join(
        item for item in (source_type, provenance, status) if item
    )
    if any(token in combined for token in ("calculated", "calculation", "deterministic")):
        return "deterministic_calculation"
    if any(token in combined for token in ("llm", "extracted")):
        return "llm_extracted"
    if any(token in combined for token in ("inferred", "candidate", "system_derived")):
        return "inferred"
    if any(token in combined for token in ("user", "structured_form", "self_declared")):
        return "user_entered"
    return "inferred"


def _normalize_confirmation_status(
    field: Mapping[str, Any],
    *,
    status: str,
    validation_status: str,
) -> str:
    raw = _token(field.get("confirmation_status"))
    allowed = {
        "unconfirmed",
        "confirmed",
        "edited_by_user",
        "explicitly_unknown",
        "rejected",
    }
    if raw in allowed:
        return raw
    if bool(field.get("explicitly_unknown")) or status == "explicitly_unknown":
        return "explicitly_unknown"
    if status in {"rejected"} or validation_status == "rejected":
        return "rejected"
    if bool(field.get("confirmation_required")) or status in {
        "candidate",
        "needs_confirmation",
        "unvalidated",
        "unknown",
        "missing",
    } or validation_status in {"candidate", "unvalidated", "unknown"}:
        return "unconfirmed"
    if status in {"confirmed", "user_confirmed", "documented", "validated", "user_stated"} or validation_status in {
        "confirmed",
        "validated",
        "documented",
        "self_declared",
        "user_stated",
    }:
        return "confirmed"
    return "unconfirmed"


def _computed_evidence_field(item: Mapping[str, Any]) -> EvidenceField:
    return EvidenceField(
        field=str(item.get("field") or "computed_value"),
        value=item.get("value"),
        unit=_optional_text(item.get("unit")),
        origin="deterministic_calculation",
        status="calculated",
        provenance="calculated",
        source_type="deterministic_calculation",
        validation_status="calculated",
        confirmation_status="confirmed",
        evidence_refs=(),
        source_span=None,
        liability_bearing=False,
        allowed_in_brief=True,
        blocked_reason=None,
    )


def _raw_case_text(
    case_row: CaseRecord,
    snapshot: CaseStateSnapshot,
    fields: Sequence[EvidenceField],
) -> str:
    state = snapshot.state_json if isinstance(snapshot.state_json, Mapping) else {}
    fragments = [
        str(getattr(case_row, "engineering_path", "") or ""),
        str(getattr(case_row, "request_type", "") or ""),
        str(state.get("raw_inquiry") or state.get("message") or ""),
    ]
    case_state = _object_mapping(state.get("case_state"))
    fragments.append(str(case_state.get("raw_inquiry") or case_state.get("user_message") or ""))
    fragments.extend(str(field.value or "") for field in fields)
    fragments.extend(str(field.source_span or "") for field in fields)
    return " ".join(fragment for fragment in fragments if fragment).strip()


def _field_satisfied(fields: Mapping[str, EvidenceField], name: str) -> bool:
    field = fields.get(name)
    if field is None:
        return False
    if field.confirmation_status == "explicitly_unknown":
        return True
    return field.allowed_in_brief and field.value not in (None, "")


def _field_text(fields: Mapping[str, EvidenceField], name: str) -> str:
    field = fields.get(name)
    if field is None or field.value is None:
        return ""
    return str(field.value)


def _truthy_field(fields: Mapping[str, EvidenceField], name: str) -> bool:
    value = _field_text(fields, name).casefold()
    return value in {"true", "yes", "ja", "1"} or value.startswith("yes") or value.startswith("ja")


def _field_number(fields: Mapping[str, EvidenceField], name: str) -> float | None:
    field = fields.get(name)
    if field is None or not field.allowed_in_brief:
        return None
    value = field.value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").replace(",", ".")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _missing_critical_fields(fields: Mapping[str, EvidenceField]) -> tuple[str, ...]:
    missing = []
    for label, alternatives in _CRITICAL_REQUIREMENTS.items():
        if not any(_field_satisfied(fields, item) for item in alternatives):
            missing.append(label)
    return tuple(missing)


def _missing_helpful_fields(fields: Mapping[str, EvidenceField]) -> tuple[str, ...]:
    return tuple(field for field in _HELPFUL_FIELDS if not _field_satisfied(fields, field))


def _speed_class(speed_mps: float | None) -> str:
    if speed_mps is None:
        return "unknown"
    if speed_mps < 2:
        return "low"
    if speed_mps < 8:
        return "medium"
    if speed_mps < 15:
        return "high"
    return "extreme"


def _pressure_class(pressure_bar: float | None) -> str:
    if pressure_bar is None:
        return "unknown"
    if pressure_bar <= 0:
        return "pressureless"
    if pressure_bar <= _STANDARD_LOW_PRESSURE_REVIEW_BAR:
        return "low_pressure"
    return "pressure_review_required"


def _temperature_class(temp_c: float | None) -> str:
    if temp_c is None:
        return "unknown"
    if temp_c < -20:
        return "low"
    if temp_c <= 100:
        return "normal"
    if temp_c <= 180:
        return "elevated"
    return "high"


def _case_type(text: str) -> str:
    lowered = text.casefold()
    if "undicht" in lowered or "leak" in lowered:
        return "leakage"
    if any(token in lowered for token in ("ersatz", "replacement", "altteil")):
        return "replacement"
    if "material" in lowered:
        return "material_change"
    return "unknown"


def _user_intent(text: str) -> str:
    lowered = text.casefold()
    if "rfq" in lowered or "anfrage" in lowered:
        return "technical_rfq_preparation"
    if "undicht" in lowered or "leak" in lowered:
        return "leakage_failure"
    if any(token in lowered for token in ("ersatz", "replacement")):
        return "replacement"
    return "unknown"


def _has_contradictions(flags: Sequence[str]) -> bool:
    return any("contradiction" in flag for flag in flags)


def _unique(items: Sequence[str] | Any) -> tuple[str, ...]:
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _blocked_reason(
    *,
    field: Mapping[str, Any],
    liability_bearing: bool,
    source_type: str,
    validation_status: str,
    status: str,
    origin: str,
    confirmation_status: str,
    source_span: str | None,
) -> str | None:
    value = field.get("value")
    if confirmation_status == "explicitly_unknown":
        return None
    if value is None or value == "":
        return "missing_value"
    if bool(field.get("confirmation_required")) and confirmation_status not in {
        "confirmed",
        "edited_by_user",
        "explicitly_unknown",
    }:
        return "explicit_user_confirmation_required"
    if not liability_bearing:
        if status in _BLOCKING_FIELD_STATUSES:
            return f"field_status_{status}"
        return None
    if origin == "user_entered":
        if status in _BLOCKING_FIELD_STATUSES:
            return f"field_status_{status}"
        return None
    if origin == "llm_extracted":
        if confirmation_status not in {"confirmed", "edited_by_user"}:
            return "llm_extracted_field_not_user_confirmed"
        if not source_span:
            return "llm_extracted_field_missing_source_span"
        if status in _BLOCKING_FIELD_STATUSES and status not in {"candidate", "needs_confirmation"}:
            return f"field_status_{status}"
        return None
    if origin == "deterministic_calculation":
        return None
    if origin == "inferred":
        return "inferred_liability_field_requires_confirmation"
    if source_type in _BLOCKING_SOURCE_TYPES:
        return f"source_type_{source_type}_not_allowed_for_brief"
    if validation_status in _BLOCKING_VALIDATION_STATUSES:
        return f"validation_status_{validation_status}_not_allowed_for_brief"
    return None


def _rwdr_scope(
    case_row: CaseRecord, fields: Sequence[EvidenceField]
) -> tuple[str, tuple[str, ...]]:
    engineering_path = str(getattr(case_row, "engineering_path", "") or "").casefold()
    if any(token in engineering_path for token in ("o-ring", "oring", "statisch", "hydraulik")):
        return "out_of_scope", (
            "Der MVP-Brief ist auf RWDR/Radialwellendichtringe begrenzt.",
        )
    if any(token in engineering_path for token in ("rwdr", "radialwellendichtring", "wellendichtring")):
        return "rwdr", ()

    scope_tokens = [
        str(getattr(case_row, "request_type", "") or ""),
    ]
    scope_tokens.extend(
        str(field.value or "")
        for field in fields
        if field.field in {"sealing_type", "seal_function", "application_pattern"}
    )
    normalized = " ".join(scope_tokens).casefold()
    if any(token in normalized for token in ("rwdr", "radialwellendichtring", "wellendichtring")):
        return "rwdr", ()
    if any(token in normalized for token in ("o-ring", "oring", "statisch", "hydraulik")):
        return "out_of_scope", (
            "Der MVP-Brief ist auf RWDR/Radialwellendichtringe begrenzt.",
        )
    return "rwdr_needs_scope_confirmation", (
        "RWDR-Bezug ist noch nicht eindeutig bestaetigt.",
    )


def _semantic_group_satisfied_by_other_field(
    field: EvidenceField, fields: Sequence[EvidenceField]
) -> bool:
    groups = tuple(
        semantic
        for semantic, aliases in _SEMANTIC_FIELD_GROUPS.items()
        if field.field in aliases
    )
    if not groups:
        return False
    allowed_names = {
        candidate.field
        for candidate in fields
        if candidate.allowed_in_brief
        and candidate.value not in (None, "")
        and candidate is not field
    }
    return any(
        any(alias in allowed_names for alias in _SEMANTIC_FIELD_GROUPS[semantic])
        for semantic in groups
    )


def _missing_required_semantics(fields: Sequence[EvidenceField]) -> tuple[str, ...]:
    allowed_by_field = {
        field.field: field
        for field in fields
        if field.allowed_in_brief and field.value not in (None, "")
    }
    missing: list[str] = []
    for semantic, aliases in _SEMANTIC_FIELD_GROUPS.items():
        if not any(alias in allowed_by_field for alias in aliases):
            missing.append(semantic)
    return tuple(missing)


def _open_points(
    missing_semantics: Sequence[str],
    blocked_fields: Sequence[EvidenceField],
    *,
    scope_reasons: Sequence[str] = (),
) -> tuple[str, ...]:
    points = [f"Missing or unconfirmed: {name}" for name in missing_semantics]
    points.extend(f"Scope clarification required: {reason}" for reason in scope_reasons)
    points.extend(
        f"{field.field}: {field.blocked_reason}"
        for field in blocked_fields
        if field.blocked_reason
    )
    return tuple(dict.fromkeys(points))


def _brief_sections(
    *,
    brief: TechnicalRWDRRFQBrief,
    canonical_case: CanonicalRWDRCase,
    evaluation: RWDREvaluation,
) -> list[dict[str, Any]]:
    confirmed = [field.as_dict() for field in brief.confirmed_case_fields]
    unconfirmed = [field.as_dict() for field in brief.open_fields]
    missing_critical = list(canonical_case.missing_critical_fields)
    missing_helpful = list(canonical_case.missing_helpful_fields)
    computed = [dict(item) for item in evaluation.computed_values]
    measurements = [dict(item) for item in evaluation.measurement_recommendations]
    sections = [
        {
            "id": "header",
            "title": "Technical RWDR RFQ Brief",
            "items": [
                {
                    "artifact_title": RWDR_MVP_ARTIFACT_TITLE,
                    "case_id": brief.case_id,
                    "case_revision": brief.case_revision,
                    "product_doctrine": "AI extracts. User confirms. sealing | Intelligence structures. Manufacturer / distributor / responsible engineer evaluates.",
                }
            ],
        },
        {"id": "status", "title": "Status", "items": [brief.status]},
        {"id": "case_type", "title": "Anfrageart", "items": [canonical_case.case_type]},
        {
            "id": "user_confirmed_application_category",
            "title": "User-confirmed application category",
            "items": [_field_text(canonical_case.canonical_fields, "application") or "unknown"],
        },
        {"id": "confirmed_data", "title": "Confirmed data", "items": confirmed},
        {"id": "unconfirmed_data", "title": "Unconfirmed data", "items": unconfirmed},
        {
            "id": "missing_critical_fields",
            "title": "Missing critical fields",
            "items": missing_critical,
        },
        {
            "id": "missing_helpful_fields",
            "title": "Missing helpful fields",
            "items": missing_helpful,
        },
        {"id": "computed_values", "title": "Computed values", "items": computed},
        {
            "id": "engineering_review_flags",
            "title": "Engineering review flags",
            "items": list(evaluation.review_flags),
        },
        {
            "id": "recommended_measurement_and_verification_data",
            "title": "Empfohlene Mess- und Prüfangaben für Herstellerbewertung",
            "items": measurements,
        },
        {
            "id": "manufacturer_questions",
            "title": "Manufacturer questions",
            "items": list(evaluation.manufacturer_questions),
        },
        {
            "id": "regulatory_and_documentation_requirements",
            "title": "Regulatory and documentation requirements",
            "items": [
                flag
                for flag in evaluation.review_flags
                if flag.endswith("_required") or "regulatory" in flag or "documentation" in flag
            ],
        },
        {
            "id": "leakage_and_service_life_expectations",
            "title": "Service-life / leakage expectations",
            "items": [
                question
                for question in evaluation.manufacturer_questions
                if "Leckage" in question or "Zielstandzeit" in question or "Wartungsintervall" in question
            ],
        },
        {
            "id": "source_evidence_summary",
            "title": "Source/evidence summary",
            "items": [
                {
                    "confirmed_field_count": len(confirmed),
                    "open_field_count": len(unconfirmed),
                    "confirmed_source_spans": [
                        {
                            "field": field.field,
                            "source_span": field.source_span,
                            "origin": field.origin,
                        }
                        for field in brief.confirmed_case_fields
                        if field.source_span
                    ],
                    "quality_metrics": dict(evaluation.quality_metrics or {}),
                }
            ],
        },
        {
            "id": "export_metadata",
            "title": "Export metadata",
            "items": [
                {
                    "schema_version": brief.schema_version,
                    "dispatch_enabled": False,
                    "manufacturer_matching_enabled": False,
                    "no_final_technical_release": True,
                }
            ],
        },
        {"id": "disclaimer", "title": "Disclaimer", "items": [_RWDR_BRIEF_DISCLAIMER]},
    ]
    return sections


def _source_span(
    field: Mapping[str, Any], *, engineering_value: Mapping[str, Any]
) -> str | None:
    for key in ("source_span", "source_excerpt", "source_text", "raw_text", "quote"):
        value = field.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raw = engineering_value.get("raw_value")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _object_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _token(value: Any) -> str:
    return str(value or "").strip().casefold()


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = tuple(value)
    else:
        items = (value,)
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _drop_none(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
