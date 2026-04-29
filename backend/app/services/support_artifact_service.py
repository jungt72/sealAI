from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType


SUPPORT_ARTIFACT_SCHEMA_VERSION = "support_artifacts_v0.8.3"
SUPPORT_ARTIFACT_TYPES: tuple[str, ...] = (
    ArtifactType.customer_reply_draft.value,
    ArtifactType.internal_engineering_note.value,
)
DEFAULT_SUPPORT_CASE_TYPE = CaseType.manufacturer_support_intake.value


@dataclass(frozen=True, slots=True)
class SupportOpenPoint:
    field: str
    reason: str
    priority: str = "medium"

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "reason": self.reason,
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class SupportEvidenceRef:
    label: str
    source_type: str
    validation_status: str
    reference: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "source_type": self.source_type,
            "validation_status": self.validation_status,
            "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class CustomerReplyDraftArtifact:
    artifact_type: str
    subject: str
    body_lines: tuple[str, ...]
    requested_information: tuple[str, ...]
    open_points: tuple[SupportOpenPoint, ...]
    boundary_notice: str
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "subject": self.subject,
            "body_lines": self.body_lines,
            "requested_information": self.requested_information,
            "open_points": [point.as_dict() for point in self.open_points],
            "boundary_notice": self.boundary_notice,
            "event_names": self.event_names,
        }


@dataclass(frozen=True, slots=True)
class InternalEngineeringNoteArtifact:
    artifact_type: str
    case_summary: str
    evidence_refs: tuple[SupportEvidenceRef, ...]
    open_points: tuple[SupportOpenPoint, ...]
    technical_notes: tuple[str, ...]
    review_actions: tuple[str, ...]
    claim_guard: tuple[str, ...]
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "case_summary": self.case_summary,
            "evidence_refs": [ref.as_dict() for ref in self.evidence_refs],
            "open_points": [point.as_dict() for point in self.open_points],
            "technical_notes": self.technical_notes,
            "review_actions": self.review_actions,
            "claim_guard": self.claim_guard,
            "event_names": self.event_names,
        }


@dataclass(frozen=True, slots=True)
class SupportArtifactBundle:
    schema_version: str
    case_type: str
    artifact_types: tuple[str, ...]
    customer_reply_draft: CustomerReplyDraftArtifact
    internal_engineering_note: InternalEngineeringNoteArtifact
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_type": self.case_type,
            "artifact_types": self.artifact_types,
            "customer_reply_draft": self.customer_reply_draft.as_dict(),
            "internal_engineering_note": self.internal_engineering_note.as_dict(),
            "event_names": self.event_names,
        }


class SupportArtifactService:
    """Create safe reply and engineering-note artifacts.

    These artifacts are drafts/projections only. They collect open points and
    evidence context without deciding cause, material limits, or commercial
    responsibility.
    """

    def build(self, payload: str | Mapping[str, Any]) -> SupportArtifactBundle:
        text = _payload_to_text(payload)
        summary = _case_summary(text)
        open_points = _open_points_from_payload(payload)
        evidence_refs = _evidence_refs_from_payload(payload)
        case_type = _case_type_from_payload(payload)

        customer_reply = _build_customer_reply(summary, open_points)
        internal_note = _build_internal_note(summary, open_points, evidence_refs)

        return SupportArtifactBundle(
            schema_version=SUPPORT_ARTIFACT_SCHEMA_VERSION,
            case_type=case_type,
            artifact_types=SUPPORT_ARTIFACT_TYPES,
            customer_reply_draft=customer_reply,
            internal_engineering_note=internal_note,
            event_names=(
                "SupportArtifactContextCollected",
                "CustomerReplyDraftGenerated",
                "InternalEngineeringNoteGenerated",
            ),
        )


def build_support_artifacts(payload: str | Mapping[str, Any]) -> SupportArtifactBundle:
    return SupportArtifactService().build(payload)


def _build_customer_reply(
    summary: str,
    open_points: Sequence[SupportOpenPoint],
) -> CustomerReplyDraftArtifact:
    requested = tuple(point.field for point in open_points)
    body_lines: list[str] = [
        "Vielen Dank fuer die Rueckmeldung. Wir bereiten den Fall als technische Klaerung auf.",
        f"Aktueller Arbeitsstand: {summary}.",
    ]
    if requested:
        body_lines.append(
            "Fuer die weitere Pruefung benoetigen wir: "
            + ", ".join(requested)
            + "."
        )
    else:
        body_lines.append(
            "Fuer die weitere Pruefung sind aktuell keine zusaetzlichen Pflichtangaben erkannt."
        )
    body_lines.extend(
        (
            "Bitte pruefen Sie Material-/Compoundgrenzen, Mediumkontakt und "
            "Betriebsbedingungen anhand Ihrer Herstellerdaten.",
            "Bis zur Rueckmeldung bleibt dies eine technische Klaerungsgrundlage.",
        )
    )
    return CustomerReplyDraftArtifact(
        artifact_type=ArtifactType.customer_reply_draft.value,
        subject="Technische Klaerung zur Dichtungsanfrage",
        body_lines=tuple(body_lines),
        requested_information=requested,
        open_points=tuple(open_points),
        boundary_notice=(
            "Entwurf fuer Rueckfragen und technische Klaerung; keine "
            "Ursachenentscheidung und keine technische Bestaetigung."
        ),
        event_names=("CustomerReplyDraftGenerated",),
    )


def _build_internal_note(
    summary: str,
    open_points: Sequence[SupportOpenPoint],
    evidence_refs: Sequence[SupportEvidenceRef],
) -> InternalEngineeringNoteArtifact:
    technical_notes = (
        f"Case summary: {summary}.",
        "Open points must remain visible in any external reply.",
        "Material and medium statements require manufacturer or compound data.",
    )
    review_actions = tuple(
        f"Clarify {point.field}: {point.reason}" for point in open_points
    ) or (
        "Check whether additional evidence or operating data is needed before response.",
    )
    return InternalEngineeringNoteArtifact(
        artifact_type=ArtifactType.internal_engineering_note.value,
        case_summary=summary,
        evidence_refs=tuple(evidence_refs),
        open_points=tuple(open_points),
        technical_notes=technical_notes,
        review_actions=review_actions,
        claim_guard=(
            "no_cause_decision",
            "no_material_limit_decision",
            "manufacturer_or_compound_review_required",
            "no_commercial_responsibility_statement",
        ),
        event_names=("InternalEngineeringNoteGenerated",),
    )


def _payload_to_text(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return payload
    values: list[str] = []
    for key in (
        "case_summary",
        "summary",
        "message",
        "text",
        "customer_message",
        "description",
    ):
        value = payload.get(key)
        if value:
            values.append(str(value))
    return "\n".join(values)


def _case_summary(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "Technischer Fall ohne belastbare Kurzbeschreibung"
    if len(normalized) <= 180:
        return normalized
    return normalized[:177].rstrip() + "..."


def _open_points_from_payload(payload: str | Mapping[str, Any]) -> tuple[SupportOpenPoint, ...]:
    if isinstance(payload, str):
        return _default_open_points()

    points: list[SupportOpenPoint] = []
    for item in _as_sequence(
        payload.get("open_points")
        or payload.get("missing_values")
        or payload.get("missing_required_fields")
    ):
        point = _coerce_open_point(item)
        if point is not None:
            points.append(point)

    if points:
        return tuple(_dedupe_open_points(points))
    return _default_open_points()


def _coerce_open_point(item: Any) -> SupportOpenPoint | None:
    if isinstance(item, Mapping):
        field = str(item.get("field") or item.get("name") or item.get("key") or "").strip()
        if not field:
            return None
        return SupportOpenPoint(
            field=field,
            reason=str(item.get("reason") or item.get("description") or "offen"),
            priority=str(item.get("priority") or "medium"),
        )
    field = str(item or "").strip()
    if not field:
        return None
    return SupportOpenPoint(field=field, reason="offene Angabe", priority="medium")


def _default_open_points() -> tuple[SupportOpenPoint, ...]:
    return (
        SupportOpenPoint(
            field="Betriebsdaten",
            reason="Druck, Temperatur und Laufprofil muessen fuer die Pruefung vorliegen.",
            priority="high",
        ),
        SupportOpenPoint(
            field="Mediumkontakt",
            reason="Medium, Konzentration und Kontaktzeit sind fuer Werkstofffragen relevant.",
            priority="high",
        ),
        SupportOpenPoint(
            field="Geometrie / Einbauraum",
            reason="Welle, Gehaeuse und Breite bestimmen die technische Klaerung.",
            priority="medium",
        ),
    )


def _evidence_refs_from_payload(
    payload: str | Mapping[str, Any],
) -> tuple[SupportEvidenceRef, ...]:
    if isinstance(payload, str):
        return ()
    refs: list[SupportEvidenceRef] = []
    for item in _as_sequence(payload.get("evidence_refs") or payload.get("documents")):
        ref = _coerce_evidence_ref(item)
        if ref is not None:
            refs.append(ref)
    return tuple(refs)


def _coerce_evidence_ref(item: Any) -> SupportEvidenceRef | None:
    if isinstance(item, Mapping):
        label = str(item.get("label") or item.get("file_name") or item.get("name") or "").strip()
        if not label:
            return None
        return SupportEvidenceRef(
            label=label,
            source_type=str(item.get("source_type") or "uploaded_evidence"),
            validation_status=str(item.get("validation_status") or "candidate"),
            reference=(
                str(item.get("reference"))
                if item.get("reference") is not None
                else None
            ),
        )
    label = str(item or "").strip()
    if not label:
        return None
    return SupportEvidenceRef(
        label=label,
        source_type="uploaded_evidence",
        validation_status="candidate",
    )


def _case_type_from_payload(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return DEFAULT_SUPPORT_CASE_TYPE
    raw_case_type = str(payload.get("case_type") or DEFAULT_SUPPORT_CASE_TYPE)
    try:
        return CaseType(raw_case_type).value
    except ValueError:
        return DEFAULT_SUPPORT_CASE_TYPE


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _dedupe_open_points(
    points: Sequence[SupportOpenPoint],
) -> tuple[SupportOpenPoint, ...]:
    seen: set[str] = set()
    deduped: list[SupportOpenPoint] = []
    for point in points:
        key = point.field.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)
    return tuple(deduped)
