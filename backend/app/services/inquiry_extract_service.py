from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


EXTRACT_SCHEMA_VERSION = "1.0.0"
DEFAULT_ARTIFACT_TYPE = "manufacturer_inquiry"
DEFAULT_SOURCE_KIND = "case_revision"

ALLOWED_TECHNICAL_FIELD_PATHS: frozenset[str] = frozenset(
    {
        "application_pattern",
        "atex_required",
        "calculated_pv_mpa_m_s",
        "calculated_speed_m_s",
        "cleaning_regime",
        "duty_cycle",
        "equipment_type",
        "food_contact_required",
        "housing_bore_diameter_mm",
        "installation_space_axial_mm",
        "installation_space_radial_mm",
        "lead_time_criticality",
        "lubrication_state",
        "medium_concentration",
        "medium_name",
        "medium_temperature_c",
        "motion_type",
        "operating_hours_per_day",
        "pressure_bar",
        "production_mode",
        "quantity_requested",
        "seal_type",
        "seal_width_mm",
        "shaft_diameter_mm",
        "shaft_hardness_hrc",
        "shaft_lead_present",
        "shaft_surface_finish",
        "speed_rpm",
        "temperature_c",
        "temperature_max_c",
        "temperature_min_c",
    }
)

ALLOWED_NORM_FIELDS: frozenset[str] = frozenset(
    {
        "module_id",
        "version",
        "status",
        "applies",
        "missing_required_fields",
        "escalation",
        "references",
    }
)

ALLOWED_ADVISORY_FIELDS: frozenset[str] = frozenset(
    {
        "advisory_id",
        "category",
        "severity",
        "reason_code",
        "triggering_parameters",
        "evidence_tags",
        "blocking",
        "disclaimer",
    }
)

ALLOWED_NEUTRAL_ARTICLE_REFERENCE_TYPES: frozenset[str] = frozenset(
    {
        "manufacturer_part_number",
        "standard_designation",
        "public_datasheet_reference",
        "drawing_reference",
    }
)

BLOCKED_ROOT_KEYS: frozenset[str] = frozenset(
    {
        "attachments",
        "contact",
        "conversation_history",
        "customer",
        "customer_metadata",
        "documents",
        "free_text_notes",
        "internal_metadata",
        "media",
        "messages",
        "photos",
        "raw_uploads",
        "user",
    }
)

BLOCKED_FIELD_TOKENS: tuple[str, ...] = (
    "address",
    "customer",
    "email",
    "exif",
    "phone",
    "project",
    "raw",
    "session",
    "user",
)


class InquiryExtractValidationError(ValueError):
    pass


class ManufacturerViewViolation(str, Enum):
    BLOCKED_ROOT_KEY = "blocked_root_key"
    BLOCKED_TECHNICAL_FIELD = "blocked_technical_field"
    BLOCKED_ARTICLE_REFERENCE = "blocked_article_reference"
    BLOCKED_NOTE = "blocked_note"


@dataclass(frozen=True, slots=True)
class InquiryExtractMeta:
    schema_version: str
    artifact_type: str
    source_kind: str
    case_id: str
    case_revision: int


@dataclass(frozen=True, slots=True)
class InquiryExtract:
    case_id: str
    tenant_id: str
    dispatched_to_manufacturer_id: str | None
    case_revision: int
    artifact_type: str
    source_kind: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ManufacturerViewValidation:
    valid: bool
    violations: tuple[dict[str, str], ...]


def build_inquiry_extract(
    context: Mapping[str, Any],
    *,
    artifact_type: str = DEFAULT_ARTIFACT_TYPE,
    source_kind: str = DEFAULT_SOURCE_KIND,
) -> InquiryExtract:
    service = InquiryExtractService()
    return service.build_inquiry_extract(
        context,
        artifact_type=artifact_type,
        source_kind=source_kind,
    )


def build_inquiry_extract_payload(context: Mapping[str, Any]) -> dict[str, Any]:
    return InquiryExtractService().build_inquiry_extract_payload(context)


def validate_manufacturer_view(payload: Mapping[str, Any]) -> ManufacturerViewValidation:
    return InquiryExtractService().validate_manufacturer_view(payload)


class InquiryExtractService:
    """Build a deterministic manufacturer-facing inquiry extract.

    This service is intentionally allowlist-first. It does not attempt broad
    PII detection; Patch 3.11 owns robust anonymization.
    """

    def build_inquiry_extract(
        self,
        context: Mapping[str, Any],
        *,
        artifact_type: str = DEFAULT_ARTIFACT_TYPE,
        source_kind: str = DEFAULT_SOURCE_KIND,
    ) -> InquiryExtract:
        case_id = _required_text(context, "case_id")
        tenant_id = _required_text(context, "tenant_id")
        case_revision = _required_int(context, "case_revision")
        if case_revision < 0:
            raise InquiryExtractValidationError("case_revision must be nonnegative")
        if artifact_type not in {"manufacturer_inquiry", "technical_summary"}:
            raise InquiryExtractValidationError("artifact_type is not supported")
        if source_kind not in {"case_revision", "manual", "migration"}:
            raise InquiryExtractValidationError("source_kind is not supported")

        payload = self.build_inquiry_extract_payload(
            context,
            artifact_type=artifact_type,
            source_kind=source_kind,
        )
        return InquiryExtract(
            case_id=case_id,
            tenant_id=tenant_id,
            dispatched_to_manufacturer_id=_optional_text(
                context.get("dispatched_to_manufacturer_id")
            ),
            case_revision=case_revision,
            artifact_type=artifact_type,
            source_kind=source_kind,
            payload=payload,
        )

    def build_inquiry_extract_payload(
        self,
        context: Mapping[str, Any],
        *,
        artifact_type: str = DEFAULT_ARTIFACT_TYPE,
        source_kind: str = DEFAULT_SOURCE_KIND,
    ) -> dict[str, Any]:
        case_id = _required_text(context, "case_id")
        case_revision = _required_int(context, "case_revision")
        request_type = _optional_text(context.get("request_type"))
        engineering_path = _optional_text(context.get("engineering_path"))
        sealing_material_family = _optional_text(context.get("sealing_material_family"))

        payload = {
            "meta": {
                "schema_version": EXTRACT_SCHEMA_VERSION,
                "artifact_type": artifact_type,
                "source_kind": source_kind,
                "case_id": case_id,
                "case_revision": case_revision,
            },
            "technical_scope": _drop_empty(
                {
                    "request_type": request_type,
                    "engineering_path": engineering_path,
                    "sealing_material_family": sealing_material_family,
                }
            ),
            "technical_parameters": _allowlisted_mapping(
                _mapping(context.get("technical_fields") or context.get("structured_fields")),
                ALLOWED_TECHNICAL_FIELD_PATHS,
            ),
            "open_points": _string_tuple(
                context.get("missing_fields") or context.get("open_points")
            ),
            "norm_compliance_signals": [
                _allowlisted_mapping(_object_mapping(item), ALLOWED_NORM_FIELDS)
                for item in _sequence(context.get("norm_results"))
            ],
            "advisory_summary": [
                _allowlisted_mapping(_object_mapping(item), ALLOWED_ADVISORY_FIELDS)
                for item in _sequence(context.get("advisory_results") or context.get("advisories"))
            ],
            "article_references": self._manufacturer_article_references(
                context.get("article_references")
            ),
            "manufacturer_facing_notes": self._manufacturer_notes(
                context.get("manufacturer_facing_notes")
            ),
            "privacy_boundary": {
                "mode": "allowlist",
                "excluded_categories": (
                    "direct_pii",
                    "customer_internal_metadata",
                    "free_text_notes",
                    "conversation_history",
                    "media_or_exif_metadata",
                    "customer_internal_article_numbers",
                ),
            },
        }
        return _drop_empty(payload)

    def validate_manufacturer_view(
        self,
        payload: Mapping[str, Any],
    ) -> ManufacturerViewValidation:
        violations: list[dict[str, str]] = []
        for key in payload:
            if str(key) in BLOCKED_ROOT_KEYS:
                violations.append(
                    {
                        "path": str(key),
                        "reason": ManufacturerViewViolation.BLOCKED_ROOT_KEY.value,
                    }
                )

        technical = _mapping(payload.get("technical_parameters"))
        for field_name in technical:
            if field_name not in ALLOWED_TECHNICAL_FIELD_PATHS or _has_blocked_token(field_name):
                violations.append(
                    {
                        "path": f"technical_parameters.{field_name}",
                        "reason": ManufacturerViewViolation.BLOCKED_TECHNICAL_FIELD.value,
                    }
                )

        for index, reference in enumerate(_sequence(payload.get("article_references"))):
            reference_mapping = _mapping(reference)
            reference_type = _optional_text(reference_mapping.get("reference_type"))
            if reference_type not in ALLOWED_NEUTRAL_ARTICLE_REFERENCE_TYPES:
                violations.append(
                    {
                        "path": f"article_references.{index}.reference_type",
                        "reason": ManufacturerViewViolation.BLOCKED_ARTICLE_REFERENCE.value,
                    }
                )

        return ManufacturerViewValidation(valid=not violations, violations=tuple(violations))

    @staticmethod
    def _manufacturer_article_references(value: Any) -> tuple[dict[str, Any], ...]:
        references: list[dict[str, Any]] = []
        for item in _sequence(value):
            record = _mapping(item)
            reference_type = _optional_text(record.get("reference_type"))
            if reference_type not in ALLOWED_NEUTRAL_ARTICLE_REFERENCE_TYPES:
                continue
            if record.get("manufacturer_visible") is not True:
                continue
            reference_value = _optional_text(record.get("value"))
            if not reference_value:
                continue
            references.append(
                _drop_empty(
                    {
                        "reference_type": reference_type,
                        "value": reference_value,
                        "source": _optional_text(record.get("source")),
                    }
                )
            )
        return tuple(references)

    @staticmethod
    def _manufacturer_notes(value: Any) -> tuple[dict[str, Any], ...]:
        notes: list[dict[str, Any]] = []
        for item in _sequence(value):
            record = _mapping(item)
            if record.get("approved_for_manufacturer") is not True:
                continue
            note_type = _optional_text(record.get("note_type"))
            note_code = _optional_text(record.get("note_code"))
            if not note_type or _has_blocked_token(note_type):
                continue
            notes.append(
                _drop_empty(
                    {
                        "note_type": note_type,
                        "note_code": note_code,
                    }
                )
            )
        return tuple(notes)


def _required_text(context: Mapping[str, Any], key: str) -> str:
    value = _optional_text(context.get(key))
    if not value:
        raise InquiryExtractValidationError(f"{key} is required")
    return value


def _required_int(context: Mapping[str, Any], key: str) -> int:
    value = context.get(key)
    if value is None or isinstance(value, bool):
        raise InquiryExtractValidationError(f"{key} is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InquiryExtractValidationError(f"{key} must be an integer") from exc


def _allowlisted_mapping(
    value: Mapping[str, Any],
    allowed_fields: frozenset[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(value):
        key_text = str(key)
        if key_text not in allowed_fields:
            continue
        if _has_blocked_token(key_text):
            continue
        sanitized = _json_safe(value[key])
        if sanitized is not None and sanitized != "" and sanitized != () and sanitized != [] and sanitized != {}:
            result[key_text] = sanitized
    return result


def _drop_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if item is not None and item != "" and item != () and item != [] and item != {}
    }


def _object_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    result: dict[str, Any] = {}
    for key in (
        "advisory_id",
        "applies",
        "blocking",
        "category",
        "disclaimer",
        "escalation",
        "evidence_tags",
        "missing_required_fields",
        "module_id",
        "reason_code",
        "references",
        "severity",
        "status",
        "triggering_parameters",
        "version",
    ):
        if hasattr(value, key):
            result[key] = getattr(value, key)
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(
        item
        for item in (_optional_text(item) for item in _sequence(value))
        if item and not _has_blocked_token(item)
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip()
    return text or None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return _drop_empty({str(key): _json_safe(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_json_safe(item) for item in value if _json_safe(item) is not None)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _has_blocked_token(value: str) -> bool:
    normalized = str(value or "").replace("-", "_").lower()
    parts = tuple(part for part in normalized.split("_") if part)
    return any(token in parts for token in BLOCKED_FIELD_TOKENS)
