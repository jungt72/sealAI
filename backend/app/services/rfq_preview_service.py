from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.models.inquiry_extract import InquiryExtractModel
from app.services.inquiry_extract_service import (
    ALLOWED_TECHNICAL_FIELD_PATHS,
    InquiryExtractService,
    validate_manufacturer_view,
)
from app.services.decision_understanding_service import (
    build_decision_understanding_payload,
)

RFQ_PREVIEW_ARTIFACT_TYPE = "rfq_preview"
RFQ_PREVIEW_SCHEMA_VERSION = "rfq_preview_v0.7.0"
RFQ_PREVIEW_SECTIONS: tuple[str, ...] = (
    "Kurzbeschreibung der Anwendung",
    "Anlage & Funktion",
    "Dichtstelle & Bewegungsart",
    "Medium & Umgebung",
    "Betriebsdaten",
    "Geometrie & Einbauraum",
    "Werkstoffe & Oberflaechen",
    "Erkannte Risiken",
    "Berechnungen / technische Hinweise",
    "Plausible technische Richtung",
    "Offene Punkte / unbestaetigte Annahmen",
    "Fragen an den Hersteller",
    "Anfrageziel / Stueckzahl / gewuenschte Rueckmeldung",
)

RFQ_FIELD_GROUP_ORDER: tuple[str, ...] = (
    "confirmed",
    "documented",
    "user_stated",
    "inferred",
    "calculated",
    "conflicting",
    "missing",
    "open",
    "needs_confirmation",
)

_RFQ_FIELD_GROUP_TITLES: dict[str, str] = {
    "confirmed": "Confirmed values",
    "documented": "Documented values",
    "user_stated": "User-stated values",
    "inferred": "Inferred candidates",
    "calculated": "Calculated values",
    "conflicting": "Conflicting values",
    "missing": "Missing critical fields",
    "open": "Open fields",
    "needs_confirmation": "Needs confirmation",
}

_FIELD_ALIASES: dict[str, str] = {
    "application_pattern_id": "application_pattern",
    "asset_type": "equipment_type",
    "calculated_pv_mpa_m_s": "calculated_pv_mpa_m_s",
    "calculated_speed_m_s": "calculated_speed_m_s",
    "equipment_type": "equipment_type",
    "medium": "medium_name",
    "medium_name": "medium_name",
    "motion_type": "motion_type",
    "pressure_nominal": "pressure_bar",
    "pressure_bar": "pressure_bar",
    "rpm": "speed_rpm",
    "shaft_diameter": "shaft_diameter_mm",
    "shaft_diameter_mm": "shaft_diameter_mm",
    "housing_bore": "housing_bore_diameter_mm",
    "housing_bore_mm": "housing_bore_diameter_mm",
    "speed_rpm": "speed_rpm",
    "surface_finish": "shaft_surface_finish",
    "temperature_c": "temperature_c",
    "temperature_max": "temperature_max_c",
    "temperature_max_c": "temperature_max_c",
    "temperature_min": "temperature_min_c",
    "temperature_min_c": "temperature_min_c",
    "food_contact": "food_contact_required",
    "atex_relevance": "atex_required",
}


class RfqPreviewError(ValueError):
    pass


class RfqPreviewNotFound(RfqPreviewError):
    pass


class RfqPreviewStaleError(RfqPreviewError):
    pass


@dataclass(frozen=True, slots=True)
class RfqPreviewView:
    preview_id: str
    case_id: str
    case_revision: int
    current_case_revision: int
    stale: bool
    consent_status: str
    dispatch_enabled: bool
    payload: dict[str, Any]
    created_at: datetime | None


class RfqPreviewService:
    """Create and govern Phase-1 RFQ preview artifacts.

    This service intentionally stops at preview/export readiness. It does not
    send to manufacturers and keeps dispatch disabled unless a later phase adds
    a separate dispatch workflow.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._extract_service = InquiryExtractService()

    async def create_preview_for_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        user_id: str,
        created_by: str,
    ) -> RfqPreviewView:
        case_row = await self._load_owned_case(case_id=case_id, tenant_id=tenant_id, user_id=user_id)
        snapshot = await self._latest_snapshot(case_id=case_id)
        if case_row is None or snapshot is None:
            raise RfqPreviewNotFound("case not found")

        revision = int(case_row.case_revision or snapshot.revision or 0)
        existing = await self._load_preview(case_id=case_id, tenant_id=tenant_id, case_revision=revision)
        if existing is not None:
            return _view(existing, current_case_revision=revision)

        payload = build_rfq_preview_payload(case_row=case_row, snapshot=snapshot)
        validation = validate_manufacturer_view(payload.get("manufacturer_extract", {}))
        if not validation.valid:
            raise RfqPreviewError("RFQ preview manufacturer view violates allowlist")

        row = InquiryExtractModel(
            case_id=str(case_row.id),
            tenant_id=str(case_row.tenant_id),
            case_revision=revision,
            artifact_type=RFQ_PREVIEW_ARTIFACT_TYPE,
            payload=payload,
            source_kind="case_revision",
            created_by=created_by,
            consent_status="not_requested",
            consent_scope={},
            dispatch_enabled=False,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _view(row, current_case_revision=revision)

    async def get_latest_preview_for_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        user_id: str,
    ) -> RfqPreviewView:
        case_row = await self._load_owned_case(case_id=case_id, tenant_id=tenant_id, user_id=user_id)
        if case_row is None:
            raise RfqPreviewNotFound("case not found")
        result = await self._session.execute(
            select(InquiryExtractModel)
            .where(InquiryExtractModel.case_id == case_id)
            .where(InquiryExtractModel.tenant_id == tenant_id)
            .where(InquiryExtractModel.artifact_type == RFQ_PREVIEW_ARTIFACT_TYPE)
            .order_by(
                InquiryExtractModel.case_revision.desc(),
                InquiryExtractModel.created_at.desc(),
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise RfqPreviewNotFound("rfq preview not found")
        return _view(row, current_case_revision=int(case_row.case_revision or 0))

    async def grant_preview_consent(
        self,
        *,
        preview_id: str,
        tenant_id: str,
        user_id: str,
        granted_by: str,
        consent_scope: Mapping[str, Any],
    ) -> RfqPreviewView:
        result = await self._session.execute(
            select(InquiryExtractModel)
            .where(InquiryExtractModel.extract_id == preview_id)
            .where(InquiryExtractModel.tenant_id == tenant_id)
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise RfqPreviewNotFound("rfq preview not found")
        case_row = await self._load_owned_case(
            case_id=str(row.case_id), tenant_id=tenant_id, user_id=user_id
        )
        if case_row is None:
            raise RfqPreviewNotFound("case not found")
        current_revision = int(case_row.case_revision or 0)
        if int(row.case_revision) != current_revision:
            raise RfqPreviewStaleError("rfq preview is stale and must be regenerated")

        normalized_scope = normalize_consent_scope(
            consent_scope,
            open_points_acknowledgement_required=_open_points_acknowledgement_required(
                row.payload
            ),
        )
        row.consent_status = "granted"
        row.consent_granted_at = datetime.now(timezone.utc)
        row.consent_granted_by = granted_by
        row.consent_scope = normalized_scope
        row.dispatch_enabled = False
        row.payload = {
            **dict(row.payload or {}),
            "consent_boundary": {
                "status": "granted",
                "scope": normalized_scope,
                "automatic_dispatch_allowed": False,
                "phase": "phase_1_preview_export_only",
            },
        }
        await self._session.commit()
        await self._session.refresh(row)
        return _view(row, current_case_revision=current_revision)

    async def _load_owned_case(
        self, *, case_id: str, tenant_id: str, user_id: str
    ) -> CaseRecord | None:
        result = await self._session.execute(
            select(CaseRecord)
            .where(CaseRecord.id == case_id)
            .where(CaseRecord.tenant_id == tenant_id)
            .where(CaseRecord.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_snapshot(self, *, case_id: str) -> CaseStateSnapshot | None:
        result = await self._session.execute(
            select(CaseStateSnapshot)
            .where(CaseStateSnapshot.case_id == case_id)
            .order_by(CaseStateSnapshot.revision.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_preview(
        self, *, case_id: str, tenant_id: str, case_revision: int
    ) -> InquiryExtractModel | None:
        result = await self._session.execute(
            select(InquiryExtractModel)
            .where(InquiryExtractModel.case_id == case_id)
            .where(InquiryExtractModel.tenant_id == tenant_id)
            .where(InquiryExtractModel.case_revision == case_revision)
            .where(InquiryExtractModel.artifact_type == RFQ_PREVIEW_ARTIFACT_TYPE)
            .limit(1)
        )
        return result.scalar_one_or_none()


def build_rfq_preview_payload(
    *, case_row: CaseRecord, snapshot: CaseStateSnapshot
) -> dict[str, Any]:
    state = snapshot.state_json if isinstance(snapshot.state_json, Mapping) else {}
    technical_fields = collect_technical_fields(case_row=case_row, state=state)
    technical_field_envelopes = collect_technical_field_envelopes(
        case_row=case_row,
        state=state,
        technical_fields=technical_fields,
    )
    technical_field_statuses = tuple(
        _technical_field_status_from_envelope(field)
        for field in technical_field_envelopes
    )
    technical_field_groups = group_technical_field_envelopes(
        technical_field_envelopes
    )
    confirmation_required_fields = tuple(
        field["field"]
        for field in technical_field_envelopes
        if field.get("confirmation_required") is True
    )
    open_points = _merge_open_points(
        collect_open_points(state),
        _confirmation_open_points(technical_field_statuses),
    )
    context = {
        "case_id": str(case_row.id),
        "tenant_id": str(case_row.tenant_id),
        "case_revision": int(case_row.case_revision or snapshot.revision or 0),
        "request_type": case_row.request_type,
        "engineering_path": case_row.engineering_path,
        "sealing_material_family": case_row.sealing_material_family,
        "technical_fields": technical_fields,
        "technical_field_statuses": technical_field_statuses,
        "technical_field_envelopes": technical_field_envelopes,
        "technical_field_groups": technical_field_groups,
        "confirmation_required_fields": confirmation_required_fields,
        "missing_fields": open_points,
        "norm_results": _deep_get_sequence(state, ("case_state", "norm_results")),
        "advisory_results": _deep_get_sequence(
            state, ("case_state", "advisory_results")
        ),
        "article_references": _deep_get_sequence(
            state, ("case_state", "article_references")
        ),
        "manufacturer_facing_notes": _deep_get_sequence(
            state, ("case_state", "manufacturer_facing_notes")
        ),
    }
    decision_understanding = build_decision_understanding_payload(
        {
            "case": context,
            "state": state,
            "technical_fields": technical_fields,
            "missing_fields": open_points,
        }
    )
    manufacturer_extract = InquiryExtractService().build_inquiry_extract_payload(
        context,
        artifact_type=RFQ_PREVIEW_ARTIFACT_TYPE,
        source_kind="case_revision",
    )
    return {
        "meta": {
            "schema_version": RFQ_PREVIEW_SCHEMA_VERSION,
            "artifact_type": RFQ_PREVIEW_ARTIFACT_TYPE,
            "case_id": str(case_row.id),
            "case_revision": int(case_row.case_revision or snapshot.revision or 0),
            "source_snapshot_revision": int(snapshot.revision),
            "source_kind": "case_revision",
            "rfq_freeze": True,
        },
        "rfq_preview": {
            "purpose": "phase_1_preview_export",
            "decision_understanding": decision_understanding,
            "technical_field_groups": technical_field_groups,
            "technical_field_envelopes": technical_field_envelopes,
            "technical_field_statuses": technical_field_statuses,
            "confirmation_required_fields": confirmation_required_fields,
            "sections": build_rfq_sections(
                technical_field_envelopes=technical_field_envelopes,
                open_points=open_points,
                state={
                    "state": state,
                    "decision_understanding": decision_understanding,
                },
            ),
            "manufacturer_release_boundary": (
                "RFQ preview for manufacturer review; no final technical release, no compliance approval."
            ),
        },
        "decision_understanding": decision_understanding,
        "manufacturer_extract": manufacturer_extract,
        "consent_boundary": {
            "status": "not_requested",
            "automatic_dispatch_allowed": False,
            "requires_explicit_user_consent_before_sharing": True,
            "open_points_acknowledgement_required": bool(open_points),
            "no_final_release_acknowledgement_required": True,
        },
    }


def collect_technical_fields(
    *, case_row: CaseRecord, state: Mapping[str, Any]
) -> dict[str, Any]:
    collected: dict[str, Any] = {}
    for key, value in {
        "application_pattern_id": case_row.application_pattern_id,
        "request_type": case_row.request_type,
        "engineering_path": case_row.engineering_path,
    }.items():
        _add_field(collected, key, value)
    for mapping in _walk_mappings(state):
        for source_key, target_key in _FIELD_ALIASES.items():
            if source_key in mapping:
                _add_field(
                    collected, target_key, _unwrap_field_value(mapping[source_key])
                )
    return {
        key: collected[key]
        for key in sorted(collected)
        if key in ALLOWED_TECHNICAL_FIELD_PATHS
    }


def collect_open_points(state: Mapping[str, Any]) -> tuple[str, ...]:
    candidates: list[str] = []
    for mapping in _walk_mappings(state):
        for key in (
            "missing_required_fields",
            "blocking_unknowns",
            "open_points",
            "not_yet_decidable",
        ):
            for item in _as_sequence(mapping.get(key)):
                text = str(item).strip()
                if text and text not in candidates:
                    candidates.append(text)
    return tuple(candidates[:24])


def collect_technical_field_statuses(state: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        _technical_field_status_from_envelope(field)
        for field in _collect_state_field_envelopes(state)
    )


def collect_technical_field_envelopes(
    *,
    case_row: CaseRecord,
    state: Mapping[str, Any],
    technical_fields: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    flat_fields = dict(
        technical_fields
        if technical_fields is not None
        else collect_technical_fields(case_row=case_row, state=state)
    )
    envelopes: dict[str, dict[str, Any]] = {
        field["field"]: field for field in _collect_state_field_envelopes(state)
    }
    for key, value in flat_fields.items():
        envelopes.setdefault(
            key,
            _drop_none(
                {
                    "field": key,
                    "value": value,
                    "status": "unspecified",
                    "provenance": "unspecified",
                    "confidence": None,
                    "confirmation_required": False,
                    "evidence_refs": (),
                }
            ),
        )

    for missing in collect_open_points(state):
        alias = _FIELD_ALIASES.get(missing, missing)
        if alias not in ALLOWED_TECHNICAL_FIELD_PATHS:
            continue
        envelopes[alias] = {
            "field": alias,
            "value": None,
            "status": "missing",
            "provenance": "missing",
            "confirmation_required": True,
            "evidence_refs": (),
        }

    return tuple(envelopes[key] for key in sorted(envelopes))


def group_technical_field_envelopes(
    fields: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    grouped: dict[str, list[dict[str, Any]]] = {
        key: [] for key in RFQ_FIELD_GROUP_ORDER
    }
    for field in fields:
        entry = dict(field)
        for key in _field_group_keys(field):
            grouped.setdefault(key, []).append(entry)
    return tuple(
        {
            "key": key,
            "title": _RFQ_FIELD_GROUP_TITLES.get(key, key),
            "fields": tuple(grouped.get(key) or ()),
        }
        for key in RFQ_FIELD_GROUP_ORDER
        if grouped.get(key)
    )


def _collect_state_field_envelopes(state: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    statuses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mapping in _walk_mappings(state):
        for source_key, target_key in _FIELD_ALIASES.items():
            if source_key not in mapping:
                continue
            value = mapping[source_key]
            if not isinstance(value, Mapping):
                continue
            alias = _FIELD_ALIASES.get(source_key, target_key)
            if alias not in ALLOWED_TECHNICAL_FIELD_PATHS or alias in seen:
                continue
            engineering_value = _engineering_value_mapping(value)
            normalized_value = _field_envelope_value(value, engineering_value)
            status = _optional_text(value.get("status") or value.get("field_status"))
            provenance = _optional_text(value.get("provenance") or value.get("source"))
            confidence = _optional_text(value.get("confidence"))
            confirmation_required = _bool_or_none(
                value.get("confirmation_required")
                if "confirmation_required" in value
                else value.get("requires_confirmation")
            )
            evidence_refs = _text_tuple(value.get("evidence_refs"))
            if not any(
                (
                    normalized_value is not None,
                    engineering_value,
                    status,
                    provenance,
                    confidence,
                    confirmation_required is not None,
                    evidence_refs,
                )
            ):
                continue
            entry = {
                "field": alias,
                "value": normalized_value,
                "engineering_value": engineering_value or None,
                "status": status or "unspecified",
                "provenance": provenance or "missing",
                "confidence": confidence,
                "confirmation_required": bool(confirmation_required),
                "evidence_refs": evidence_refs,
                "source_revision": _optional_int(value.get("source_revision")),
            }
            statuses.append(_drop_none(entry))
            seen.add(alias)
    return tuple(statuses)


def build_rfq_sections(
    *,
    technical_field_envelopes: Sequence[Mapping[str, Any]],
    open_points: Sequence[str],
    state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    top_risks = tuple(
        str(item)
        for item in _as_sequence(
            _first_value_for_keys(state, ("top_risks", "key_risks", "risks"))
        )
    )
    manufacturer_questions = tuple(
        str(item)
        for item in _as_sequence(
            _first_value_for_keys(
                state, ("manufacturer_review_needs", "manufacturer_questions")
            )
        )
    )
    values = {
        str(field.get("field")): _section_field_value(field)
        for field in technical_field_envelopes
        if field.get("field")
    }
    section_payloads: tuple[Any, ...] = (
        _pick(values, "equipment_type", "medium_name", "motion_type"),
        _pick(values, "equipment_type", "application_pattern"),
        _pick(values, "motion_type", "seal_type"),
        _pick(
            values,
            "medium_name",
            "medium_concentration",
            "food_contact_required",
            "atex_required",
        ),
        _pick(
            values,
            "temperature_c",
            "temperature_min_c",
            "temperature_max_c",
            "pressure_bar",
            "speed_rpm",
        ),
        _pick(
            values,
            "shaft_diameter_mm",
            "housing_bore_diameter_mm",
            "seal_width_mm",
            "shaft_surface_finish",
        ),
        _pick(
            values,
            "sealing_material_family",
            "shaft_hardness_hrc",
            "shaft_lead_present",
        ),
        top_risks,
        _pick(values, "calculated_speed_m_s", "calculated_pv_mpa_m_s"),
        tuple(
            str(item)
            for item in _as_sequence(
                _first_value_for_keys(
                    state, ("plausible_directions", "technical_direction")
                )
            )
        ),
        tuple(open_points),
        manufacturer_questions or _default_manufacturer_questions(open_points),
        _pick(values, "quantity_requested", "lead_time_criticality", "production_mode"),
    )
    return [
        {
            "index": index,
            "title": title,
            "content": section_payloads[index - 1],
            "status": "available" if section_payloads[index - 1] else "open",
        }
        for index, title in enumerate(RFQ_PREVIEW_SECTIONS, start=1)
    ]


def normalize_consent_scope(
    value: Mapping[str, Any],
    *,
    open_points_acknowledgement_required: bool = False,
) -> dict[str, Any]:
    scope = dict(value or {})
    shared_sections = tuple(
        str(item).strip()
        for item in _as_sequence(scope.get("shared_sections"))
        if str(item).strip()
    )
    shared_documents = tuple(
        str(item).strip()
        for item in _as_sequence(scope.get("shared_documents"))
        if str(item).strip()
    )
    intended_recipients = tuple(
        str(item).strip()
        for item in _as_sequence(scope.get("intended_recipients"))
        if str(item).strip()
    )
    if not shared_sections:
        raise RfqPreviewError("consent_scope.shared_sections is required")
    if not intended_recipients:
        raise RfqPreviewError("consent_scope.intended_recipients is required")
    user_acknowledged_no_final_release = bool(
        scope.get("user_acknowledged_no_final_release")
    )
    user_acknowledged_open_points = bool(
        scope.get("user_acknowledged_open_points")
    )
    if not user_acknowledged_no_final_release:
        raise RfqPreviewError(
            "user_acknowledged_no_final_release is required for RFQ preview consent"
        )
    if open_points_acknowledgement_required and not user_acknowledged_open_points:
        raise RfqPreviewError(
            "user_acknowledged_open_points is required while RFQ preview has open points"
        )
    return {
        "shared_sections": shared_sections,
        "shared_documents": shared_documents,
        "intended_recipients": intended_recipients,
        "user_acknowledged_open_points": user_acknowledged_open_points,
        "user_acknowledged_no_final_release": user_acknowledged_no_final_release,
    }


def _view(row: InquiryExtractModel, *, current_case_revision: int) -> RfqPreviewView:
    return RfqPreviewView(
        preview_id=str(row.extract_id),
        case_id=str(row.case_id),
        case_revision=int(row.case_revision),
        current_case_revision=current_case_revision,
        stale=int(row.case_revision) != int(current_case_revision),
        consent_status=str(row.consent_status),
        dispatch_enabled=bool(row.dispatch_enabled),
        payload=dict(row.payload or {}),
        created_at=row.created_at,
    )


def _open_points_acknowledgement_required(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    consent_boundary = payload.get("consent_boundary")
    if isinstance(consent_boundary, Mapping):
        return bool(consent_boundary.get("open_points_acknowledgement_required"))
    return False


def _add_field(target: dict[str, Any], key: str, value: Any) -> None:
    alias = _FIELD_ALIASES.get(key, key)
    if alias not in ALLOWED_TECHNICAL_FIELD_PATHS:
        return
    normalized = _unwrap_field_value(value)
    if normalized is not None and normalized != "":
        target[alias] = normalized


def _unwrap_field_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        for key in ("canonical_value", "value", "raw_value", "label", "name"):
            if key in value:
                return _unwrap_field_value(value[key])
        return {str(key): _unwrap_field_value(item) for key, item in value.items()}
    return value


def _walk_mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    found: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        found.append(value)
        for item in value.values():
            found.extend(_walk_mappings(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            found.extend(_walk_mappings(item))
    return tuple(found)


def _deep_get_sequence(
    mapping: Mapping[str, Any], path: tuple[str, ...]
) -> tuple[Any, ...]:
    current: Any = mapping
    for part in path:
        if not isinstance(current, Mapping):
            return ()
        current = current.get(part)
    return _as_sequence(current)


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _first_value_for_keys(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for item in _walk_mappings(mapping):
        for key in keys:
            if key in item and item[key]:
                return item[key]
    return None


def _pick(mapping: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {
        key: mapping[key]
        for key in keys
        if key in mapping and mapping[key] not in (None, "", (), [], {})
    }


def _default_manufacturer_questions(open_points: Sequence[str]) -> tuple[str, ...]:
    if not open_points:
        return (
            "Bitte technische Eignung und offene Auslegungsdaten herstellerseitig pruefen.",
        )
    return tuple(f"Bitte klaeren: {point}" for point in open_points[:6])


def _confirmation_open_points(
    field_statuses: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    result: list[str] = []
    open_statuses = {
        "candidate",
        "conflict",
        "inferred",
        "invalid",
        "needs_confirmation",
        "stale",
        "unconfirmed",
    }
    for field in field_statuses:
        field_name = str(field.get("field") or "").strip()
        if not field_name:
            continue
        status = str(field.get("status") or "").strip()
        requires_confirmation = bool(field.get("confirmation_required"))
        if not requires_confirmation and status not in open_statuses:
            continue
        suffix = f" (status: {status})" if status else ""
        result.append(f"Bestaetigung erforderlich: {field_name}{suffix}")
    return tuple(result)


def _technical_field_status_from_envelope(field: Mapping[str, Any]) -> dict[str, Any]:
    evidence_refs = tuple(_as_sequence(field.get("evidence_refs")))
    return _drop_none(
        {
            "field": field.get("field"),
            "status": field.get("status"),
            "provenance": field.get("provenance"),
            "confidence": field.get("confidence"),
            "confirmation_required": bool(field.get("confirmation_required")),
            "evidence_refs": evidence_refs or None,
        }
    )


def _field_group_keys(field: Mapping[str, Any]) -> tuple[str, ...]:
    status = str(field.get("status") or "").strip().lower()
    provenance = str(field.get("provenance") or "").strip().lower()
    confirmation_required = bool(field.get("confirmation_required"))
    keys: list[str] = []
    if status in {"conflict", "conflicting"}:
        keys.append("conflicting")
    elif status == "missing" or provenance == "missing":
        keys.append("missing")
    elif status == "calculated" or provenance == "calculated":
        keys.append("calculated")
    elif status == "confirmed":
        keys.append("confirmed")
    elif status == "documented" or provenance == "documented":
        keys.append("documented")
    elif status == "user_stated" or provenance == "user_stated":
        keys.append("user_stated")
    elif status == "inferred" or provenance in {"inferred", "pattern_derived"}:
        keys.append("inferred")
    elif status in {"candidate", "open", "unknown", "unspecified"}:
        keys.append("open")
    else:
        keys.append("open")

    if confirmation_required or status in {
        "candidate",
        "conflict",
        "conflicting",
        "inferred",
        "missing",
        "needs_confirmation",
        "open",
        "stale",
    }:
        keys.append("needs_confirmation")
    return tuple(dict.fromkeys(keys))


def _field_envelope_value(
    field: Mapping[str, Any], engineering_value: Mapping[str, Any]
) -> Any:
    if engineering_value.get("canonical_value") is not None:
        return engineering_value.get("canonical_value")
    for key in ("canonical_value", "value", "raw_value", "label", "name"):
        if key in field:
            return _unwrap_field_value(field[key])
    return None


def _engineering_value_mapping(field: Mapping[str, Any]) -> dict[str, Any]:
    value = field.get("engineering_value")
    if isinstance(value, Mapping):
        return _drop_none(
            {str(key): _unwrap_field_value(item) for key, item in value.items()}
        )
    return _drop_none(
        {
            "raw_value": _unwrap_field_value(field.get("raw_value")),
            "canonical_value": _unwrap_field_value(field.get("canonical_value")),
            "unit": _optional_text(field.get("unit")),
            "quantity_kind": _optional_text(field.get("quantity_kind")),
            "interpretation": _optional_text(field.get("interpretation")),
        }
    )


def _section_field_value(field: Mapping[str, Any]) -> dict[str, Any]:
    engineering_value = _object_mapping(field.get("engineering_value"))
    unit = engineering_value.get("unit")
    evidence_refs = tuple(_as_sequence(field.get("evidence_refs")))
    return _drop_none(
        {
            "value": field.get("value"),
            "unit": unit,
            "status": field.get("status") or "unspecified",
            "provenance": field.get("provenance") or "missing",
            "confirmation_required": bool(field.get("confirmation_required")),
            "evidence_refs": evidence_refs or None,
        }
    )


def _text_tuple(value: Any) -> tuple[str, ...]:
    return tuple(
        str(item).strip()
        for item in _as_sequence(value)
        if str(item).strip()
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _object_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _merge_open_points(*groups: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in result:
                result.append(text)
    return tuple(result[:24])


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "ja"}:
            return True
        if normalized in {"false", "0", "no", "nein"}:
            return False
    return bool(value)


def _drop_none(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in mapping.items() if value is not None}
