from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType


SHALLOW_MODE_SCHEMA_VERSION = "shallow_mode_intake_v0.8.3"


@dataclass(frozen=True, slots=True)
class ShallowModeArtifact:
    case_type: str
    artifact_type: str
    status: str
    evidence_refs: tuple[str, ...]
    open_points: tuple[str, ...]
    next_question: str
    boundary_notice: str
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_type": self.case_type,
            "artifact_type": self.artifact_type,
            "status": self.status,
            "evidence_refs": self.evidence_refs,
            "open_points": self.open_points,
            "next_question": self.next_question,
            "boundary_notice": self.boundary_notice,
            "event_names": self.event_names,
        }


@dataclass(frozen=True, slots=True)
class ShallowModeIntakeBundle:
    schema_version: str
    primary_case_type: str
    artifact_type: str
    artifact: ShallowModeArtifact
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "primary_case_type": self.primary_case_type,
            "artifact_type": self.artifact_type,
            "artifact": self.artifact.as_dict(),
            "event_names": self.event_names,
        }


class ShallowModeIntakeService:
    """Create safe shallow intakes for secondary v0.8.3 scenarios."""

    def build(self, payload: str | Mapping[str, Any]) -> ShallowModeIntakeBundle:
        text = _payload_to_text(payload)
        evidence_refs = _evidence_refs(payload)
        case_type = _infer_case_type(payload, text, evidence_refs)
        artifact = _build_artifact(case_type, evidence_refs)
        return ShallowModeIntakeBundle(
            schema_version=SHALLOW_MODE_SCHEMA_VERSION,
            primary_case_type=case_type.value,
            artifact_type=artifact.artifact_type,
            artifact=artifact,
            event_names=(
                "ShallowModeIntentIdentified",
                "CaseTypeAssigned",
                "ShallowIntakeGenerated",
            ),
        )


def build_shallow_mode_intake(
    payload: str | Mapping[str, Any],
) -> ShallowModeIntakeBundle:
    return ShallowModeIntakeService().build(payload)


def _build_artifact(
    case_type: CaseType,
    evidence_refs: tuple[str, ...],
) -> ShallowModeArtifact:
    if case_type is CaseType.drawing_review:
        return ShallowModeArtifact(
            case_type=case_type.value,
            artifact_type=ArtifactType.drawing_review.value,
            status="candidate_review",
            evidence_refs=evidence_refs,
            open_points=(
                "Zeichnungsrevision",
                "Werkstoff und Oberflaechenangaben",
                "Toleranzen und kritische Masse",
                "Anwendungskontext",
            ),
            next_question="Welche Zeichnungsrevision und Anwendung gehoeren zu diesem Teil?",
            boundary_notice=(
                "Zeichnung wird als Evidence behandelt; Herstellbarkeit "
                "bleibt zu pruefen."
            ),
            event_names=("DrawingReviewIntakeGenerated",),
        )
    if case_type is CaseType.quote_comparison:
        return ShallowModeArtifact(
            case_type=case_type.value,
            artifact_type=ArtifactType.quote_comparison.value,
            status="candidate_comparison",
            evidence_refs=evidence_refs,
            open_points=(
                "technischer Angebotsumfang",
                "Werkstoff- und Nachweisangaben",
                "Lieferumfang und Ausschluesse",
                "Abgleich gegen RFQ-Anforderung",
            ),
            next_question=(
                "Welche technische Anforderung soll zuerst gegen die "
                "Angebote geprueft werden?"
            ),
            boundary_notice=(
                "Angebote werden strukturiert verglichen; Preis allein "
                "bestimmt keine technische Richtung."
            ),
            event_names=("QuoteComparisonIntakeGenerated",),
        )
    if case_type is CaseType.material_substitution:
        return ShallowModeArtifact(
            case_type=case_type.value,
            artifact_type=ArtifactType.material_substitution_brief.value,
            status="risk_brief_candidate",
            evidence_refs=evidence_refs,
            open_points=(
                "Ausgangswerkstoff",
                "Zielanforderung der Substitution",
                "Medium, Temperatur und Bewegung",
                "Nachweise oder Ausschlusskriterien",
            ),
            next_question="Welcher Werkstoff soll ersetzt werden und welches Medium liegt an?",
            boundary_notice=(
                "Substitution bleibt Risikobrief; Alternativen benoetigen "
                "Hersteller- oder Compoundpruefung."
            ),
            event_names=("MaterialSubstitutionBriefGenerated",),
        )
    return ShallowModeArtifact(
        case_type=CaseType.emergency_mro.value,
        artifact_type=ArtifactType.emergency_triage.value,
        status="urgent_triage",
        evidence_refs=evidence_refs,
        open_points=(
            "Stillstandsauswirkung",
            "Dichtstelle und Altteilangaben",
            "sofort verfuegbare Fotos oder Masse",
            "kritische Betriebsgrenzen",
        ),
        next_question=(
            "Welche eine Information entscheidet jetzt am staerksten: "
            "Altteilfoto, Masse oder Dichtstelle?"
        ),
        boundary_notice="Emergency-Triage erzeugt keine Bestellung und keinen Dispatch.",
        event_names=("EmergencyTriageGenerated",),
    )


def _infer_case_type(
    payload: str | Mapping[str, Any],
    text: str,
    evidence_refs: tuple[str, ...],
) -> CaseType:
    if isinstance(payload, Mapping):
        raw = str(payload.get("case_type") or "")
        try:
            case_type = CaseType(raw)
            if case_type in _SUPPORTED_CASE_TYPES:
                return case_type
        except ValueError:
            pass

    normalized = text.casefold()
    if any(token in normalized for token in ("anlage steht", "notfall", "sofort", "heute ersatz")):
        return CaseType.emergency_mro
    if any(token in normalized for token in ("angebot", "angebote", "quote", "preisvergleich")):
        return CaseType.quote_comparison
    if any(token in normalized for token in ("pfas", "alternative", "ersetzen", "substitution")):
        return CaseType.material_substitution
    if evidence_refs or any(token in normalized for token in ("zeichnung", "drawing", "gefertigt")):
        return CaseType.drawing_review
    return CaseType.drawing_review


def _payload_to_text(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return payload
    values: list[str] = []
    for key in ("text", "message", "description", "request", "file_name"):
        value = payload.get(key)
        if value:
            values.append(str(value))
    return "\n".join(values)


def _evidence_refs(payload: str | Mapping[str, Any]) -> tuple[str, ...]:
    if isinstance(payload, str):
        return ()
    refs: list[str] = []
    for item in _as_sequence(payload.get("evidence_refs") or payload.get("documents")):
        if isinstance(item, Mapping):
            label = item.get("label") or item.get("file_name") or item.get("name")
            if label:
                refs.append(str(label))
        elif item:
            refs.append(str(item))
    return tuple(dict.fromkeys(refs))


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


_SUPPORTED_CASE_TYPES = {
    CaseType.drawing_review,
    CaseType.quote_comparison,
    CaseType.material_substitution,
    CaseType.emergency_mro,
}
