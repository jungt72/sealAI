from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.models.inquiry_extract import InquiryExtractModel
from app.domain.artifact_type import ArtifactType
from app.domain.source_validation import source_validation_metadata
from app.services.inquiry_extract_service import (
    ALLOWED_TECHNICAL_FIELD_PATHS,
    InquiryExtractService,
    validate_manufacturer_view,
)
from app.services.decision_understanding_service import (
    build_decision_understanding_payload,
)

RFQ_PREVIEW_ARTIFACT_TYPE = ArtifactType.rfq_preview.value
RFQ_PREVIEW_SCHEMA_VERSION = "rfq_preview_v0.7.0"
RFQ_PREVIEW_CONTRACT_VERSION = "rfq_preview_contract_v0.8.3"
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


@dataclass(frozen=True, slots=True)
class RFQExportDocument:
    export_generated: bool
    preview_id: str
    case_id: str
    case_revision: int
    generated_from_case_revision: int
    artifact_type: str
    export_format: str
    dispatch_enabled: bool
    automatic_dispatch_allowed: bool
    no_final_technical_release: bool
    included_sections: tuple[str, ...]
    excluded_sections: tuple[str, ...]
    omitted_disallowed_content: tuple[str, ...]
    content: dict[str, Any]
    event_names: tuple[str, ...]
    created_at: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "export_generated": self.export_generated,
            "preview_id": self.preview_id,
            "case_id": self.case_id,
            "case_revision": self.case_revision,
            "generated_from_case_revision": self.generated_from_case_revision,
            "artifact_type": self.artifact_type,
            "export_format": self.export_format,
            "dispatch_enabled": self.dispatch_enabled,
            "automatic_dispatch_allowed": self.automatic_dispatch_allowed,
            "no_final_technical_release": self.no_final_technical_release,
            "included_sections": self.included_sections,
            "excluded_sections": self.excluded_sections,
            "omitted_disallowed_content": self.omitted_disallowed_content,
            "content": self.content,
            "event_names": self.event_names,
            "created_at": self.created_at,
        }


RFQExportPayload = dict[str, Any]


class RfqExportBlockedError(RfqPreviewError):
    def __init__(self, message: str, *, event_names: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.event_names = tuple(event_names) or (
            "ExportBlocked",
            "ExternalDispatchBlocked",
            "RFQDispatchDisabled",
        )


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
        expected_case_revision: int | None = None,
    ) -> RfqPreviewView:
        case_row = await self._load_owned_case(case_id=case_id, tenant_id=tenant_id, user_id=user_id)
        snapshot = await self._latest_snapshot(case_id=case_id)
        if case_row is None or snapshot is None:
            raise RfqPreviewNotFound("case not found")

        revision = int(case_row.case_revision or snapshot.revision or 0)
        if expected_case_revision is not None and int(expected_case_revision) != revision:
            raise RfqPreviewStaleError(
                "case revision changed; refresh the case before creating an RFQ preview"
            )
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
            **_harden_rfq_payload_contract(
                row.payload,
                case_revision=int(row.case_revision),
                current_case_revision=current_revision,
            ),
            "consent_boundary": {
                "status": "granted",
                "scope": normalized_scope,
                "required_acknowledgements": _required_acknowledgements(
                    open_points_acknowledgement_required=_open_points_acknowledgement_required(
                        row.payload
                    ),
                    matching_included=False,
                ),
                "automatic_dispatch_allowed": False,
                "dispatch_enabled": False,
                "phase": "phase_1_preview_export_only",
            },
        }
        await self._session.commit()
        await self._session.refresh(row)
        return _view(row, current_case_revision=current_revision)

    async def generate_export(
        self,
        *,
        preview_id: str,
        tenant_id: str,
        user_id: str,
    ) -> RFQExportDocument:
        result = await self._session.execute(
            select(InquiryExtractModel)
            .where(InquiryExtractModel.extract_id == preview_id)
            .where(InquiryExtractModel.tenant_id == tenant_id)
            .where(InquiryExtractModel.artifact_type == RFQ_PREVIEW_ARTIFACT_TYPE)
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

        raw_payload = row.payload if isinstance(row.payload, Mapping) else {}
        _require_dispatch_disabled(row, payload=raw_payload)
        payload = _harden_rfq_payload_contract(
            row.payload,
            case_revision=int(row.case_revision),
            current_case_revision=current_revision,
        )
        consent_scope = _require_export_consent(row, payload=payload)
        _require_dispatch_disabled(row, payload=payload)

        return build_rfq_export_document(
            row=row,
            payload=payload,
            consent_scope=consent_scope,
            current_case_revision=current_revision,
        )

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
    source_validation_summary = build_source_validation_summary(
        technical_field_envelopes
    )
    open_points_summary = build_open_points_summary(open_points)
    evidence_refs_summary = build_evidence_refs_summary(technical_field_envelopes)
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
            "contract_version": RFQ_PREVIEW_CONTRACT_VERSION,
            "artifact_type": RFQ_PREVIEW_ARTIFACT_TYPE,
            "case_id": str(case_row.id),
            "case_revision": int(case_row.case_revision or snapshot.revision or 0),
            "generated_from_case_revision": int(
                case_row.case_revision or snapshot.revision or 0
            ),
            "source_snapshot_revision": int(snapshot.revision),
            "source_kind": "case_revision",
            "rfq_freeze": True,
            "preview_status": "current",
            "no_final_technical_release": True,
            "dispatch_enabled": False,
            "automatic_dispatch_allowed": False,
        },
        "rfq_preview": {
            "purpose": "phase_1_preview_export",
            "artifact_type": RFQ_PREVIEW_ARTIFACT_TYPE,
            "case_revision": int(case_row.case_revision or snapshot.revision or 0),
            "generated_from_case_revision": int(
                case_row.case_revision or snapshot.revision or 0
            ),
            "preview_status": "current",
            "no_final_technical_release": True,
            "dispatch_enabled": False,
            "automatic_dispatch_allowed": False,
            "decision_understanding": decision_understanding,
            "technical_field_groups": technical_field_groups,
            "technical_field_envelopes": technical_field_envelopes,
            "technical_field_statuses": technical_field_statuses,
            "confirmation_required_fields": confirmation_required_fields,
            "source_validation_summary": source_validation_summary,
            "open_points_summary": open_points_summary,
            "evidence_refs_summary": evidence_refs_summary,
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
        "source_validation_summary": source_validation_summary,
        "open_points_summary": open_points_summary,
        "evidence_refs_summary": evidence_refs_summary,
        "consent_boundary": {
            "status": "not_requested",
            "automatic_dispatch_allowed": False,
            "dispatch_enabled": False,
            "requires_explicit_user_consent_before_sharing": True,
            "open_points_acknowledgement_required": bool(open_points),
            "no_final_release_acknowledgement_required": True,
            "export_intent_acknowledgement_required": True,
            "required_acknowledgements": _required_acknowledgements(
                open_points_acknowledgement_required=bool(open_points),
                matching_included=False,
            ),
        },
    }


def build_rfq_export_document(
    *,
    row: InquiryExtractModel,
    payload: Mapping[str, Any],
    consent_scope: Mapping[str, Any],
    current_case_revision: int,
) -> RFQExportDocument:
    meta = _object_mapping(payload.get("meta"))
    rfq_preview = _object_mapping(payload.get("rfq_preview"))
    generated_from_case_revision = int(
        meta.get("generated_from_case_revision")
        or rfq_preview.get("generated_from_case_revision")
        or row.case_revision
    )
    sections, excluded_sections = _allowlisted_export_sections(
        rfq_preview.get("sections"),
        consent_scope=consent_scope,
    )
    technical_fields = _allowlisted_export_technical_fields(
        rfq_preview.get("technical_field_envelopes")
        or rfq_preview.get("technical_field_statuses")
    )
    evidence_refs = _allowlisted_evidence_refs(
        tuple(rfq_preview.get("evidence_refs_summary", {}).get("items", ()))
        if isinstance(rfq_preview.get("evidence_refs_summary"), Mapping)
        else ()
    )
    if not evidence_refs:
        evidence_refs = _allowlisted_evidence_refs(
            ref
            for field in technical_fields
            for ref in _as_sequence(field.get("evidence_refs"))
        )
    content = _drop_empty(
        {
            "title": "RFQ Preview - Anfragebasis fuer Herstellerpruefung",
            "safe_case_reference": {"case_id": str(row.case_id)},
            "preview_reference": {"preview_id": str(row.extract_id)},
            "revision": {
                "case_revision": int(row.case_revision),
                "generated_from_case_revision": generated_from_case_revision,
                "current_case_revision": int(current_case_revision),
            },
            "notices": {
                "no_final_technical_release": True,
                "manufacturer_review_required": True,
                "notice": "No final technical release. Manufacturer review required.",
            },
            "technical_fields": technical_fields,
            "open_points": _allowlisted_text_sequence(
                _open_points_for_export(rfq_preview, sections)
            ),
            "risks": _allowlisted_text_sequence(_risks_for_export(sections, payload)),
            "manufacturer_review_notes": _allowlisted_text_sequence(
                _manufacturer_review_notes_for_export(sections, payload)
            ),
            "evidence_references": evidence_refs,
            "source_validation_summary": _allowlisted_source_validation_summary(
                rfq_preview.get("source_validation_summary")
                or payload.get("source_validation_summary")
            ),
            "consent_acknowledgement_summary": _consent_export_summary(consent_scope),
        }
    )
    included_sections = tuple(content.keys())
    omitted = (
        "raw_preview_payload",
        "raw_uploaded_document_content",
        "internal_paths",
        "secrets_or_tokens",
        "non_allowlisted_metadata",
        "external_dispatch",
    )
    return RFQExportDocument(
        export_generated=True,
        preview_id=str(row.extract_id),
        case_id=str(row.case_id),
        case_revision=int(row.case_revision),
        generated_from_case_revision=generated_from_case_revision,
        artifact_type=RFQ_PREVIEW_ARTIFACT_TYPE,
        export_format="json",
        dispatch_enabled=False,
        automatic_dispatch_allowed=False,
        no_final_technical_release=True,
        included_sections=included_sections,
        excluded_sections=excluded_sections + omitted,
        omitted_disallowed_content=omitted,
        content=content,
        event_names=(
            "RFQConsentGranted",
            "ExportGenerated",
            "ExternalDispatchBlocked",
            "RFQDispatchDisabled",
        ),
        created_at=row.created_at,
    )


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

    return tuple(
        _enrich_technical_field_envelope(envelopes[key]) for key in sorted(envelopes)
    )


def build_source_validation_summary(
    fields: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_source_type: dict[str, int] = {}
    by_validation_status: dict[str, int] = {}
    for field in fields:
        source_type = str(field.get("source_type") or "unknown")
        validation_status = str(field.get("validation_status") or "unknown")
        by_source_type[source_type] = by_source_type.get(source_type, 0) + 1
        by_validation_status[validation_status] = (
            by_validation_status.get(validation_status, 0) + 1
        )
    return {
        "total_fields": len(tuple(fields)),
        "by_source_type": by_source_type,
        "by_validation_status": by_validation_status,
        "unvalidated_count": by_validation_status.get("unvalidated", 0),
        "candidate_count": by_validation_status.get("candidate", 0),
        "conflicting_count": by_validation_status.get("conflicting", 0),
        "unknown_count": by_validation_status.get("unknown", 0),
        "not_final_release": True,
    }


def build_open_points_summary(open_points: Sequence[str]) -> dict[str, Any]:
    items = tuple(str(item).strip() for item in open_points if str(item).strip())
    return {
        "count": len(items),
        "items": items,
        "acknowledgement_required": bool(items),
    }


def build_evidence_refs_summary(
    fields: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    refs: list[str] = []
    for field in fields:
        for ref in _as_sequence(field.get("evidence_refs")):
            text = str(ref).strip()
            if text and text not in refs:
                refs.append(text)
    return {
        "count": len(refs),
        "items": tuple(refs),
    }


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
    user_acknowledged_export_intent = bool(
        scope.get("user_acknowledged_export_intent")
    )
    if not user_acknowledged_no_final_release:
        raise RfqPreviewError(
            "user_acknowledged_no_final_release is required for RFQ preview consent"
        )
    if not user_acknowledged_export_intent:
        raise RfqPreviewError(
            "user_acknowledged_export_intent is required for RFQ preview consent"
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
        "user_acknowledged_export_intent": user_acknowledged_export_intent,
    }


def _require_export_consent(
    row: InquiryExtractModel,
    *,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if str(row.consent_status) != "granted":
        raise RfqExportBlockedError("RFQ preview consent is required before export")
    consent_scope = row.consent_scope if isinstance(row.consent_scope, Mapping) else {}
    try:
        return normalize_consent_scope(
            consent_scope,
            open_points_acknowledgement_required=_open_points_acknowledgement_required(
                payload
            ),
        )
    except RfqPreviewError as exc:
        raise RfqExportBlockedError(str(exc)) from exc


def _require_dispatch_disabled(
    row: InquiryExtractModel,
    *,
    payload: Mapping[str, Any],
) -> None:
    consent_boundary = _object_mapping(payload.get("consent_boundary"))
    meta = _object_mapping(payload.get("meta"))
    rfq_preview = _object_mapping(payload.get("rfq_preview"))
    if bool(row.dispatch_enabled):
        raise RfqExportBlockedError("RFQ dispatch must remain disabled for manual export")
    if any(
        bool(mapping.get("dispatch_enabled"))
        for mapping in (consent_boundary, meta, rfq_preview)
    ):
        raise RfqExportBlockedError("RFQ dispatch must remain disabled for manual export")
    if any(
        bool(mapping.get("automatic_dispatch_allowed"))
        for mapping in (consent_boundary, meta, rfq_preview)
    ):
        raise RfqExportBlockedError("automatic dispatch is not allowed for manual export")


def _allowlisted_export_sections(
    value: Any,
    *,
    consent_scope: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    consented = {
        str(item).strip()
        for item in _as_sequence(consent_scope.get("shared_sections"))
        if str(item).strip()
    }
    include_all = bool(
        {"rfq_preview", "RFQ-Preview", "RFQ Preview", "preview"}.intersection(consented)
    )
    allowed_titles = set(RFQ_PREVIEW_SECTIONS)
    sections: list[dict[str, Any]] = []
    excluded: list[str] = []
    for item in _as_sequence(value):
        section = _object_mapping(item)
        title = _optional_text(section.get("title"))
        if not title:
            continue
        if title not in allowed_titles:
            excluded.append("non_allowlisted_section")
            continue
        if not include_all and title not in consented:
            excluded.append("section_not_in_consent_scope")
            continue
        content = _safe_json_value(section.get("content"))
        sections.append(
            _drop_empty(
                {
                    "index": _optional_int(section.get("index")),
                    "title": title,
                    "status": _safe_text(section.get("status")),
                    "content": content,
                }
            )
        )
    return tuple(sections), tuple(dict.fromkeys(excluded))


def _allowlisted_export_technical_fields(value: Any) -> tuple[dict[str, Any], ...]:
    fields: list[dict[str, Any]] = []
    for item in _as_sequence(value):
        field = _object_mapping(item)
        field_key = _optional_text(field.get("field") or field.get("field_key"))
        if field_key not in ALLOWED_TECHNICAL_FIELD_PATHS:
            continue
        engineering_value = _object_mapping(field.get("engineering_value"))
        fields.append(
            _drop_empty(
                {
                    "field": field_key,
                    "label": _safe_text(field.get("label")),
                    "value": _safe_json_value(field.get("value")),
                    "engineering_value": _allowlisted_engineering_value(
                        engineering_value
                    ),
                    "unit": _safe_text(field.get("unit")),
                    "normalized_value": _safe_json_value(field.get("normalized_value")),
                    "normalized_unit": _safe_text(field.get("normalized_unit")),
                    "status": _safe_text(field.get("status")),
                    "source_type": _safe_text(field.get("source_type")),
                    "validation_status": _safe_text(field.get("validation_status")),
                    "confirmation_required": bool(field.get("confirmation_required")),
                    "evidence_refs": _allowlisted_evidence_refs(
                        field.get("evidence_refs")
                    ),
                }
            )
        )
    return tuple(fields)


def _allowlisted_engineering_value(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "raw_value",
        "canonical_value",
        "unit",
        "quantity_kind",
        "interpretation",
    }
    return _drop_empty(
        {
            key: _safe_json_value(value.get(key))
            for key in sorted(allowed)
            if key in value
        }
    )


def _open_points_for_export(
    rfq_preview: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
) -> tuple[Any, ...]:
    summary = _object_mapping(rfq_preview.get("open_points_summary"))
    items = _as_sequence(summary.get("items"))
    if items:
        return items
    return tuple(
        content
        for section in sections
        if "Offene Punkte" in str(section.get("title") or "")
        for content in _flatten_text_items(section.get("content"))
    )


def _risks_for_export(
    sections: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
) -> tuple[Any, ...]:
    decision = _object_mapping(payload.get("decision_understanding"))
    return (
        tuple(
            content
            for section in sections
            if "Risiken" in str(section.get("title") or "")
            for content in _flatten_text_items(section.get("content"))
        )
        + _as_sequence(decision.get("key_risks"))
    )


def _manufacturer_review_notes_for_export(
    sections: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
) -> tuple[Any, ...]:
    decision = _object_mapping(payload.get("decision_understanding"))
    return (
        tuple(
            content
            for section in sections
            if "Fragen an den Hersteller" in str(section.get("title") or "")
            for content in _flatten_text_items(section.get("content"))
        )
        + _as_sequence(decision.get("manufacturer_review_needs"))
    )


def _allowlisted_source_validation_summary(value: Any) -> dict[str, Any]:
    summary = _object_mapping(value)
    return _drop_empty(
        {
            "total_fields": _optional_int(summary.get("total_fields")),
            "by_source_type": _safe_count_mapping(summary.get("by_source_type")),
            "by_validation_status": _safe_count_mapping(
                summary.get("by_validation_status")
            ),
            "unvalidated_count": _optional_int(summary.get("unvalidated_count")),
            "candidate_count": _optional_int(summary.get("candidate_count")),
            "conflicting_count": _optional_int(summary.get("conflicting_count")),
            "unknown_count": _optional_int(summary.get("unknown_count")),
            "not_final_release": True,
        }
    )


def _consent_export_summary(consent_scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "granted",
        "user_acknowledged_no_final_release": bool(
            consent_scope.get("user_acknowledged_no_final_release")
        ),
        "user_acknowledged_open_points": bool(
            consent_scope.get("user_acknowledged_open_points")
        ),
        "user_acknowledged_export_intent": bool(
            consent_scope.get("user_acknowledged_export_intent")
        ),
        "shared_sections": _allowlisted_text_sequence(
            consent_scope.get("shared_sections")
        ),
        "shared_document_refs": _allowlisted_evidence_refs(
            consent_scope.get("shared_documents")
        ),
        "manual_export_only": True,
    }


def _safe_count_mapping(value: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, item in _object_mapping(value).items():
        text = _safe_text(key)
        if not text:
            continue
        number = _optional_int(item)
        if number is not None:
            result[text] = number
    return result


def _allowlisted_text_sequence(value: Any) -> tuple[str, ...]:
    result: list[str] = []
    for item in _as_sequence(value):
        text = _safe_text(item)
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _allowlisted_evidence_refs(value: Any) -> tuple[str, ...]:
    result: list[str] = []
    for item in _as_sequence(value):
        text = _safe_text(item)
        if not text or text == "[REDACTED]":
            continue
        if not _is_safe_reference(text):
            continue
        if text not in result:
            result.append(text)
    return tuple(result[:48])


def _flatten_text_items(value: Any) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(
            text
            for key, item in value.items()
            for text in _flatten_text_items(f"{key}: {item}")
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(text for item in value for text in _flatten_text_items(item))
    text = _safe_text(value)
    return (text,) if text else ()


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _drop_empty(
            {str(key): _safe_json_value(item) for key, item in value.items()}
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(
            item
            for item in (_safe_json_value(item) for item in value)
            if item not in (None, "", (), [], {})
        )
    return _safe_text(value) if isinstance(value, str) else value


def _safe_text(value: Any) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    if _looks_like_internal_path(text) or _looks_like_secret(text):
        return "[REDACTED]"
    return text[:500]


def _is_safe_reference(value: str) -> bool:
    if _looks_like_internal_path(value) or _looks_like_secret(value):
        return False
    if "/" in value or "\\" in value:
        return False
    allowed_prefixes = (
        "chat:",
        "document:",
        "evidence:",
        "paperless:",
        "rag:",
        "source:",
        "upload:",
    )
    if value.startswith(allowed_prefixes):
        return True
    return all(char.isalnum() or char in {"-", "_", ".", "#", ":"} for char in value)


def _looks_like_internal_path(value: str) -> bool:
    lowered = value.casefold()
    if lowered.startswith(("file://", "/")):
        return True
    if ":\\" in value or "\\\\" in value:
        return True
    return any(
        marker in lowered
        for marker in (
            "/home/",
            "/tmp/",
            "/var/",
            "/etc/",
            "/usr/",
            ".env",
        )
    )


def _looks_like_secret(value: str) -> bool:
    lowered = value.casefold()
    secret_markers = (
        "api_key",
        "apikey",
        "authorization:",
        "bearer ",
        "client_secret",
        "password",
        "private_key",
        "secret=",
        "token=",
    )
    return any(marker in lowered for marker in secret_markers)


def _view(row: InquiryExtractModel, *, current_case_revision: int) -> RfqPreviewView:
    return RfqPreviewView(
        preview_id=str(row.extract_id),
        case_id=str(row.case_id),
        case_revision=int(row.case_revision),
        current_case_revision=current_case_revision,
        stale=int(row.case_revision) != int(current_case_revision),
        consent_status=str(row.consent_status),
        dispatch_enabled=bool(row.dispatch_enabled),
        payload=_harden_rfq_payload_contract(
            row.payload,
            case_revision=int(row.case_revision),
            current_case_revision=current_case_revision,
        ),
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
    if "source_type" not in field or "validation_status" not in field:
        field = _enrich_technical_field_envelope(field)
    evidence_refs = tuple(_as_sequence(field.get("evidence_refs")))
    return _drop_none(
        {
            "field": field.get("field"),
            "field_key": field.get("field_key") or field.get("field"),
            "label": field.get("label"),
            "status": field.get("status"),
            "provenance": field.get("provenance"),
            "source_type": field.get("source_type"),
            "validation_status": field.get("validation_status"),
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
    unit = field.get("unit") or engineering_value.get("unit")
    evidence_refs = tuple(_as_sequence(field.get("evidence_refs")))
    return _drop_none(
        {
            "value": field.get("value"),
            "unit": unit,
            "normalized_value": field.get("normalized_value"),
            "normalized_unit": field.get("normalized_unit"),
            "status": field.get("status") or "unspecified",
            "provenance": field.get("provenance") or "missing",
            "source_type": field.get("source_type") or "unknown",
            "validation_status": field.get("validation_status") or "unknown",
            "confirmation_required": bool(field.get("confirmation_required")),
            "evidence_refs": evidence_refs or None,
        }
    )


def _enrich_technical_field_envelope(field: Mapping[str, Any]) -> dict[str, Any]:
    field_key = str(field.get("field") or field.get("field_key") or "").strip()
    status = _optional_text(field.get("status")) or "unspecified"
    provenance = field.get("provenance")
    conflict = status.lower() in {"conflict", "conflicting"}
    metadata = source_validation_metadata(
        status=status,
        provenance=provenance,
        origin=field.get("origin"),
        source_type=field.get("source_type"),
        validation_status=field.get("validation_status"),
        conflict=conflict,
    )
    engineering_value = _object_mapping(field.get("engineering_value"))
    normalized_value = field.get("normalized_value")
    if normalized_value is None:
        normalized_value = engineering_value.get("canonical_value")
    normalized_unit = field.get("normalized_unit") or engineering_value.get("unit")
    unit = field.get("unit") or engineering_value.get("unit")
    notes = tuple(_text_tuple(field.get("notes")))
    enriched = {
        **dict(field),
        "field": field_key,
        "field_key": field_key,
        "label": field.get("label") or _field_label(field_key),
        "unit": unit,
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "source_type": metadata.source_type.value,
        "validation_status": metadata.validation_status.value,
        "authoritative": metadata.authoritative,
        "not_for_release_decisions": metadata.not_for_release_decisions,
        "source_validation_events": metadata.event_names,
        "notes": notes or None,
    }
    result = _drop_none(enriched)
    if "value" in field and "value" not in result:
        result["value"] = None
    return result


def _field_label(field_key: str) -> str:
    return field_key.replace("_", " ").strip().title() if field_key else "Field"


def _required_acknowledgements(
    *,
    open_points_acknowledgement_required: bool,
    matching_included: bool,
) -> dict[str, bool]:
    return {
        "user_acknowledged_no_final_release": True,
        "user_acknowledged_open_points": bool(open_points_acknowledgement_required),
        "user_acknowledged_export_intent": True,
        "user_acknowledged_partner_network_disclosure": bool(matching_included),
    }


def _harden_rfq_payload_contract(
    payload: Any,
    *,
    case_revision: int,
    current_case_revision: int,
) -> dict[str, Any]:
    result = dict(payload) if isinstance(payload, Mapping) else {}
    stale = int(case_revision) != int(current_case_revision)
    preview_status = "stale" if stale else "current"
    meta = dict(result.get("meta") if isinstance(result.get("meta"), Mapping) else {})
    meta.update(
        {
            "contract_version": meta.get(
                "contract_version", RFQ_PREVIEW_CONTRACT_VERSION
            ),
            "artifact_type": RFQ_PREVIEW_ARTIFACT_TYPE,
            "case_revision": int(case_revision),
            "generated_from_case_revision": int(
                meta.get("generated_from_case_revision") or case_revision
            ),
            "preview_status": preview_status,
            "no_final_technical_release": True,
            "dispatch_enabled": False,
            "automatic_dispatch_allowed": False,
        }
    )
    result["meta"] = meta

    rfq_preview = dict(
        result.get("rfq_preview")
        if isinstance(result.get("rfq_preview"), Mapping)
        else {}
    )
    rfq_preview.update(
        {
            "artifact_type": RFQ_PREVIEW_ARTIFACT_TYPE,
            "case_revision": int(case_revision),
            "generated_from_case_revision": int(
                rfq_preview.get("generated_from_case_revision") or case_revision
            ),
            "preview_status": preview_status,
            "no_final_technical_release": True,
            "dispatch_enabled": False,
            "automatic_dispatch_allowed": False,
        }
    )
    result["rfq_preview"] = rfq_preview

    open_points_required = _open_points_acknowledgement_required(result)
    consent_boundary = dict(
        result.get("consent_boundary")
        if isinstance(result.get("consent_boundary"), Mapping)
        else {}
    )
    consent_boundary.update(
        {
            "automatic_dispatch_allowed": False,
            "dispatch_enabled": False,
            "no_final_release_acknowledgement_required": True,
            "export_intent_acknowledgement_required": True,
            "required_acknowledgements": _required_acknowledgements(
                open_points_acknowledgement_required=open_points_required,
                matching_included=False,
            ),
        }
    )
    result["consent_boundary"] = consent_boundary
    return result


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


def _drop_empty(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in mapping.items()
        if value is not None and value != "" and value != () and value != [] and value != {}
    }
