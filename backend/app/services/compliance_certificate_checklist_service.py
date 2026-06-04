from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType


COMPLIANCE_CHECKLIST_SCHEMA_VERSION = "compliance_checklist_v0.8.3"
COMPLIANCE_CHECKLIST_ARTIFACT_TYPE = ArtifactType.compliance_checklist.value
COMPLIANCE_CHECKLIST_CASE_TYPE = CaseType.compliance_certificate_request.value

_MATERIAL_RE = re.compile(r"\b(FKM|NBR|EPDM|PTFE|FFKM|VMQ|HNBR)\b", re.IGNORECASE)
_COMPOUND_RE = re.compile(
    r"\b(?:compound|mischung|grade|type|typ)\s*[:#-]?\s*"
    r"(?P<value>[A-Z0-9][A-Z0-9._/-]{2,})\b",
    re.IGNORECASE,
)
_STANDARD_PATTERNS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "FDA",
        ("fda", "21 cfr", "food contact", "lebensmittelkontakt"),
        (
            "exakte Compound- oder Gradebezeichnung",
            "Herstellererklaerung fuer den genannten Kontaktfall",
            "Chargen- oder Traceability-Bezug",
            "Einsatzmedium, Temperatur und Kontaktzeit",
        ),
    ),
    (
        "EU 1935/2004",
        ("1935/2004", "ec 1935", "eu 1935"),
        (
            "Kontext der Lebensmittelkontakt-Anforderung",
            "Herstellererklaerung mit Material- und Artikelbezug",
            "Rueckverfolgbarkeit der Charge",
        ),
    ),
    (
        "EU 10/2011",
        ("10/2011", "eu 10"),
        (
            "Kunststoff- oder Compoundbezug",
            "Migrations- oder Erklaerungsdokument",
            "Kontaktmedium und Temperaturbereich",
        ),
    ),
    (
        "USP Class VI",
        ("usp class vi", "usp vi", "usp klasse vi"),
        (
            "spezifischer Compound",
            "Pruefbericht oder Herstellererklaerung",
            "Anwendungs- und Chargenbezug",
        ),
    ),
    (
        "ATEX",
        ("atex", "explosionsschutz", "zone 0", "zone 1", "zone 2"),
        (
            "ATEX-Zone und Geraete-/Anlagenkontext",
            "Mediumzustand und Entzuendungsrisiko",
            "Herstellerbewertung der Dichtstelle",
        ),
    ),
    (
        "TA-Luft",
        ("ta-luft", "ta luft", "emission", "fugitive"),
        (
            "Nachweisziel und Grenzwertkontext",
            "Dichtsystem und Betriebsbedingungen",
            "Hersteller- oder Pruefdokument",
        ),
    ),
    (
        "EHEDG",
        ("ehedg", "hygienic design", "hygienic"),
        (
            "Hygienic-Design-Kontext",
            "Reinigungsprozess",
            "Herstellerdokument fuer die konkrete Baugruppe",
        ),
    ),
    (
        "Trinkwasser",
        ("trinkwasser", "ktw", "dvgw", "nsf"),
        (
            "Zielmarkt und geforderter Trinkwassernachweis",
            "Material-/Compound- und Artikelbezug",
            "Temperatur- und Kontaktbereich",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ComplianceMaterialContext:
    material_family: str | None
    compound_identifier: str | None
    status: str
    open_points: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "material_family": self.material_family,
            "compound_identifier": self.compound_identifier,
            "status": self.status,
            "open_points": self.open_points,
        }


@dataclass(frozen=True, slots=True)
class ComplianceRequirement:
    standard: str
    source_type: str
    evidence_status: str
    required_evidence: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "standard": self.standard,
            "source_type": self.source_type,
            "evidence_status": self.evidence_status,
            "required_evidence": self.required_evidence,
            "evidence_refs": self.evidence_refs,
        }


@dataclass(frozen=True, slots=True)
class ComplianceChecklistItem:
    topic: str
    status: str
    explanation: str
    required_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "status": self.status,
            "explanation": self.explanation,
            "required_action": self.required_action,
        }


@dataclass(frozen=True, slots=True)
class ComplianceCertificateChecklistArtifact:
    schema_version: str
    case_type: str
    artifact_type: str
    material_context: ComplianceMaterialContext
    requirements: tuple[ComplianceRequirement, ...]
    checklist: tuple[ComplianceChecklistItem, ...]
    open_evidence: tuple[str, ...]
    boundary_notice: str
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_type": self.case_type,
            "artifact_type": self.artifact_type,
            "material_context": self.material_context.as_dict(),
            "requirements": [
                requirement.as_dict() for requirement in self.requirements
            ],
            "checklist": [item.as_dict() for item in self.checklist],
            "open_evidence": self.open_evidence,
            "boundary_notice": self.boundary_notice,
            "event_names": self.event_names,
        }


class ComplianceCertificateChecklistService:
    """Build evidence-oriented compliance certificate request checklists."""

    def build(
        self,
        payload: str | Mapping[str, Any],
    ) -> ComplianceCertificateChecklistArtifact:
        text = _payload_to_text(payload)
        material_context = _material_context(text)
        evidence_refs = _evidence_refs(payload)
        requirements = _requirements(text, evidence_refs)
        open_evidence = _open_evidence(material_context, requirements)
        checklist = _checklist(material_context, requirements)

        return ComplianceCertificateChecklistArtifact(
            schema_version=COMPLIANCE_CHECKLIST_SCHEMA_VERSION,
            case_type=COMPLIANCE_CHECKLIST_CASE_TYPE,
            artifact_type=COMPLIANCE_CHECKLIST_ARTIFACT_TYPE,
            material_context=material_context,
            requirements=requirements,
            checklist=checklist,
            open_evidence=open_evidence,
            boundary_notice=(
                "Checkliste fuer Nachweis- und Zertifikatsanforderungen. "
                "Materialfamilie, Compound, Anwendung und Dokumente werden "
                "getrennt bewertet; eine belastbare Aussage benoetigt passende "
                "Hersteller- oder Pruefdokumente."
            ),
            event_names=(
                "ComplianceCertificateRequestIdentified",
                "ComplianceRequirementCaptured",
                "ComplianceEvidenceMarkedOpen",
                "ComplianceChecklistGenerated",
            ),
        )


def build_compliance_certificate_checklist(
    payload: str | Mapping[str, Any],
) -> ComplianceCertificateChecklistArtifact:
    return ComplianceCertificateChecklistService().build(payload)


def _payload_to_text(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return payload
    values: list[str] = []
    for key in (
        "text",
        "message",
        "description",
        "material",
        "certificate_request",
        "requirements",
    ):
        value = payload.get(key)
        if value:
            values.append(str(value))
    return "\n".join(values)


def _material_context(text: str) -> ComplianceMaterialContext:
    material = _extract_material(text)
    compound = _extract_compound(text)
    open_points: list[str] = []
    if material and not compound:
        open_points.append("compound_identifier")
    if not material:
        open_points.append("material_family")
    status = "candidate" if material or compound else "missing"
    if material and compound:
        status = "candidate_with_compound"
    return ComplianceMaterialContext(
        material_family=material,
        compound_identifier=compound,
        status=status,
        open_points=tuple(open_points),
    )


def _extract_material(text: str) -> str | None:
    match = _MATERIAL_RE.search(text)
    return match.group(1).upper() if match else None


def _extract_compound(text: str) -> str | None:
    match = _COMPOUND_RE.search(text)
    return match.group("value") if match else None


def _requirements(
    text: str,
    evidence_refs: tuple[str, ...],
) -> tuple[ComplianceRequirement, ...]:
    normalized = text.casefold()
    requirements: list[ComplianceRequirement] = []
    for standard, triggers, required_evidence in _STANDARD_PATTERNS:
        if not any(trigger in normalized for trigger in triggers):
            continue
        requirements.append(
            ComplianceRequirement(
                standard=standard,
                source_type="user_stated",
                evidence_status=(
                    "candidate_evidence_present"
                    if evidence_refs
                    else "required_missing"
                ),
                required_evidence=required_evidence,
                evidence_refs=evidence_refs,
            )
        )
    if requirements:
        return tuple(requirements)
    return (
        ComplianceRequirement(
            standard="unspecified_certificate_requirement",
            source_type="user_stated",
            evidence_status="required_missing",
            required_evidence=(
                "benoetigter Standard oder Zielmarkt",
                "Material- und Compoundbezug",
                "Anwendung und Mediumkontakt",
            ),
            evidence_refs=evidence_refs,
        ),
    )


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


def _open_evidence(
    material_context: ComplianceMaterialContext,
    requirements: Sequence[ComplianceRequirement],
) -> tuple[str, ...]:
    open_items: list[str] = list(material_context.open_points)
    for requirement in requirements:
        if requirement.evidence_status == "required_missing":
            open_items.append(f"{requirement.standard}.evidence")
        for evidence in requirement.required_evidence:
            open_items.append(f"{requirement.standard}: {evidence}")
    return tuple(dict.fromkeys(open_items))


def _checklist(
    material_context: ComplianceMaterialContext,
    requirements: Sequence[ComplianceRequirement],
) -> tuple[ComplianceChecklistItem, ...]:
    items: list[ComplianceChecklistItem] = [
        ComplianceChecklistItem(
            topic="Materialfamilie",
            status=material_context.status,
            explanation=(
                "Werkstofffamilie ist nur ein Hinweis; der konkrete Compound "
                "und der Dokumentbezug bleiben getrennte Pruefpunkte."
            ),
            required_action="Compound, Artikel- und Chargenbezug klaeren.",
        )
    ]
    for requirement in requirements:
        items.append(
            ComplianceChecklistItem(
                topic=requirement.standard,
                status=requirement.evidence_status,
                explanation=(
                    "Anforderung wurde als Nachweisthema erkannt; vorhandene "
                    "Dokumente muessen zum konkreten Fall passen."
                ),
                required_action=(
                    "Passende Hersteller- oder Pruefdokumente mit Scope, "
                    "Material und Anwendungskontext bereitstellen."
                ),
            )
        )
    return tuple(items)


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)
