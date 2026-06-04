from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType


REPLACEMENT_LEGACY_SCHEMA_VERSION = "replacement_legacy_part_v0.8.3"
REPLACEMENT_LEGACY_ARTIFACT_TYPES: tuple[str, ...] = (
    ArtifactType.replacement_sheet.value,
    ArtifactType.legacy_part_intake.value,
)

_DIMENSION_RE = re.compile(
    r"\b(?P<shaft>\d{1,4}(?:[,.]\d+)?)\s*[xX*]\s*"
    r"(?P<bore>\d{1,4}(?:[,.]\d+)?)\s*[xX*]\s*"
    r"(?P<width>\d{1,4}(?:[,.]\d+)?)\b"
)
_ARTICLE_RE = re.compile(
    r"\b(?:artikel|artikelnummer|teilenummer|part|pn|erp)\s*[:#-]?\s*"
    r"(?P<value>[A-Z0-9][A-Z0-9._/-]{2,})\b",
    re.IGNORECASE,
)
_MATERIAL_RE = re.compile(r"\b(FKM|NBR|EPDM|PTFE|FFKM|VMQ)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LegacyPartCandidate:
    dimensions: dict[str, float] | None
    markings: tuple[str, ...]
    material_hint: str | None
    article_number: str | None
    source_type: str
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimensions": self.dimensions,
            "markings": self.markings,
            "material_hint": self.material_hint,
            "article_number": self.article_number,
            "source_type": self.source_type,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class IdentityConfidence:
    level: str
    score: float
    drivers: tuple[str, ...]
    open_points: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "score": self.score,
            "drivers": self.drivers,
            "open_points": self.open_points,
        }


@dataclass(frozen=True, slots=True)
class ReplacementLegacyArtifact:
    artifact_type: str
    case_type: str
    part_candidate: LegacyPartCandidate
    identity_confidence: IdentityConfidence
    required_evidence: tuple[str, ...]
    boundary_notice: str
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "case_type": self.case_type,
            "part_candidate": self.part_candidate.as_dict(),
            "identity_confidence": self.identity_confidence.as_dict(),
            "required_evidence": self.required_evidence,
            "boundary_notice": self.boundary_notice,
            "event_names": self.event_names,
        }


@dataclass(frozen=True, slots=True)
class ReplacementLegacyBundle:
    schema_version: str
    primary_case_type: str
    artifact_types: tuple[str, ...]
    replacement_sheet: ReplacementLegacyArtifact
    legacy_part_intake: ReplacementLegacyArtifact
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "primary_case_type": self.primary_case_type,
            "artifact_types": self.artifact_types,
            "replacement_sheet": self.replacement_sheet.as_dict(),
            "legacy_part_intake": self.legacy_part_intake.as_dict(),
            "event_names": self.event_names,
        }


class ReplacementLegacyPartService:
    """Structure old-part and reorder context without identity certainty."""

    def build(self, payload: str | Mapping[str, Any]) -> ReplacementLegacyBundle:
        text = _payload_to_text(payload)
        candidate = _extract_candidate(text, payload)
        evidence_present = _has_evidence(payload)
        required_evidence = _required_evidence(candidate, evidence_present)
        identity = _identity_confidence(candidate, evidence_present, required_evidence)
        primary_case_type = _infer_case_type(payload, text)

        replacement = ReplacementLegacyArtifact(
            artifact_type=ArtifactType.replacement_sheet.value,
            case_type=CaseType.replacement_reorder.value,
            part_candidate=candidate,
            identity_confidence=identity,
            required_evidence=required_evidence,
            boundary_notice=(
                "Replacement Sheet: Identitaet und Austauschbarkeit bleiben "
                "zu bestaetigen."
            ),
            event_names=("ReplacementSheetGenerated",),
        )
        legacy = ReplacementLegacyArtifact(
            artifact_type=ArtifactType.legacy_part_intake.value,
            case_type=CaseType.unknown_legacy_part.value,
            part_candidate=candidate,
            identity_confidence=identity,
            required_evidence=required_evidence,
            boundary_notice=(
                "Legacy Part Intake: Altteilangaben sind Kandidaten, bis "
                "Fotos, Masse und Anwendungskontext geprueft wurden."
            ),
            event_names=("LegacyPartIntakeGenerated",),
        )
        return ReplacementLegacyBundle(
            schema_version=REPLACEMENT_LEGACY_SCHEMA_VERSION,
            primary_case_type=primary_case_type,
            artifact_types=REPLACEMENT_LEGACY_ARTIFACT_TYPES,
            replacement_sheet=replacement,
            legacy_part_intake=legacy,
            event_names=(
                "ReplacementLegacyContextCollected",
                "LegacyPartCandidateExtracted",
                "IdentityConfidenceComputed",
                "ReplacementSheetGenerated",
                "LegacyPartIntakeGenerated",
            ),
        )


def build_replacement_legacy_part_intake(
    payload: str | Mapping[str, Any],
) -> ReplacementLegacyBundle:
    return ReplacementLegacyPartService().build(payload)


def _payload_to_text(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return payload
    values: list[str] = []
    for key in (
        "text",
        "message",
        "description",
        "part_marking",
        "article_number",
        "erp_data",
    ):
        value = payload.get(key)
        if value:
            values.append(str(value))
    return "\n".join(values)


def _extract_candidate(
    text: str,
    payload: str | Mapping[str, Any],
) -> LegacyPartCandidate:
    dimensions = _extract_dimensions(text)
    article_number = _extract_article_number(text, payload)
    material_hint = _extract_material(text)
    markings = _extract_markings(text, article_number, material_hint)
    return LegacyPartCandidate(
        dimensions=dimensions,
        markings=markings,
        material_hint=material_hint,
        article_number=article_number,
        source_type="user_stated",
        status="candidate",
    )


def _extract_dimensions(text: str) -> dict[str, float] | None:
    match = _DIMENSION_RE.search(text)
    if not match:
        return None
    return {
        "shaft_diameter_mm": _to_float(match.group("shaft")),
        "housing_bore_mm": _to_float(match.group("bore")),
        "width_mm": _to_float(match.group("width")),
    }


def _extract_article_number(
    text: str,
    payload: str | Mapping[str, Any],
) -> str | None:
    if isinstance(payload, Mapping):
        explicit = payload.get("article_number") or payload.get("part_number")
        if explicit:
            return str(explicit)
    match = _ARTICLE_RE.search(text)
    return match.group("value") if match else None


def _extract_material(text: str) -> str | None:
    match = _MATERIAL_RE.search(text)
    return match.group(1).upper() if match else None


def _extract_markings(
    text: str,
    article_number: str | None,
    material_hint: str | None,
) -> tuple[str, ...]:
    markings: list[str] = []
    dimension = _DIMENSION_RE.search(text)
    if dimension:
        markings.append(dimension.group(0))
    if article_number:
        markings.append(article_number)
    if material_hint:
        markings.append(material_hint)
    return tuple(dict.fromkeys(markings))


def _has_evidence(payload: str | Mapping[str, Any]) -> bool:
    if isinstance(payload, str):
        return False
    evidence = (
        payload.get("evidence_refs")
        or payload.get("photos")
        or payload.get("documents")
    )
    if evidence is None:
        return False
    if isinstance(evidence, (str, bytes)):
        return bool(evidence)
    if isinstance(evidence, Sequence):
        return bool(evidence)
    return True


def _required_evidence(
    candidate: LegacyPartCandidate,
    evidence_present: bool,
) -> tuple[str, ...]:
    required: list[str] = []
    if not evidence_present:
        required.extend(
            (
                "Foto der Beschriftung",
                "Foto von Vorder- und Rueckseite",
                "Foto der Einbausituation",
            )
        )
    if candidate.dimensions is None:
        required.append("Masse: Welle, Gehaeuse, Breite")
    else:
        required.append("Messmethode und Toleranzen der Masse")
    if candidate.material_hint is None:
        required.append("Werkstoff- oder Haerteangabe")
    required.append("Anwendungskontext und Medium")
    return tuple(dict.fromkeys(required))


def _identity_confidence(
    candidate: LegacyPartCandidate,
    evidence_present: bool,
    required_evidence: Sequence[str],
) -> IdentityConfidence:
    drivers: list[str] = []
    score = 0.0
    if candidate.dimensions:
        score += 0.25
        drivers.append("dimensions_present")
    if candidate.article_number:
        score += 0.25
        drivers.append("article_number_present")
    if candidate.material_hint:
        score += 0.15
        drivers.append("material_hint_present")
    if evidence_present:
        score += 0.2
        drivers.append("evidence_present")
    if score >= 0.65:
        level = "medium"
    elif score >= 0.25:
        level = "low"
    else:
        level = "unknown"
    return IdentityConfidence(
        level=level,
        score=round(score, 2),
        drivers=tuple(drivers) or ("insufficient_identifiers",),
        open_points=tuple(required_evidence),
    )


def _infer_case_type(payload: str | Mapping[str, Any], text: str) -> str:
    if isinstance(payload, Mapping):
        raw = str(payload.get("case_type") or "")
        try:
            case_type = CaseType(raw)
            if case_type in {
                CaseType.replacement_reorder,
                CaseType.unknown_legacy_part,
            }:
                return case_type.value
        except ValueError:
            pass

    normalized = text.casefold()
    if any(
        token in normalized for token in ("steht nur", "nur", "unbekannt", "altteil")
    ):
        return CaseType.unknown_legacy_part.value
    return CaseType.replacement_reorder.value


def _to_float(value: str) -> float:
    return float(value.replace(",", "."))
