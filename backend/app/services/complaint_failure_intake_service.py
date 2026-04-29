from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType


COMPLAINT_FAILURE_SCHEMA_VERSION = "complaint_failure_intake_v0.8.3"
COMPLAINT_FAILURE_ARTIFACT_TYPES: tuple[str, ...] = (
    ArtifactType.complaint_intake.value,
    ArtifactType.failure_analysis_intake.value,
)

_DURATION_RE = re.compile(
    r"\bnach\s+(?P<value>\d+(?:[,.]\d+)?)\s*"
    r"(?P<unit>stunden|tage|wochen|monaten|monate|jahren|jahre|h|d)\b",
    re.IGNORECASE,
)
_PRESSURE_RE = re.compile(r"\b(?P<value>\d+(?:[,.]\d+)?)\s*bar\b", re.IGNORECASE)
_TEMPERATURE_RE = re.compile(
    r"\b(?P<value>\d+(?:[,.]\d+)?)\s*(?:degc|c|grad|°c)\b",
    re.IGNORECASE,
)
_RPM_RE = re.compile(
    r"\b(?P<value>\d+(?:[,.]\d+)?)\s*(?:rpm|u/min|1/min)\b",
    re.IGNORECASE,
)
_DAMAGE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("leakage", ("leckt", "leckage", "undicht", "oelverlust", "verlust")),
    ("premature_failure", ("ausgefallen", "haelt nur", "nach 3 monaten", "kurzer laufzeit")),
    ("wear", ("verschleiss", "verschlissen", "abgerieben", "riefen")),
    ("crack_or_break", ("riss", "gerissen", "gebrochen", "bruch")),
    ("thermal_damage", ("verbrannt", "verhaertet", "hart geworden", "ueberhitzt")),
    ("swelling_or_chemical_attack", ("aufgequollen", "quillt", "chemisch", "angegriffen")),
)


@dataclass(frozen=True, slots=True)
class DamagePatternCandidate:
    pattern: str
    label: str
    status: str
    source_type: str
    evidence_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "label": self.label,
            "status": self.status,
            "source_type": self.source_type,
            "evidence_required": self.evidence_required,
        }


@dataclass(frozen=True, slots=True)
class OperatingConditionCandidate:
    field: str
    raw_value: str
    status: str
    source_type: str = "user_stated"

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "raw_value": self.raw_value,
            "status": self.status,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class ComplaintFailureIntakeArtifact:
    artifact_type: str
    case_type: str
    damage_patterns: tuple[DamagePatternCandidate, ...]
    operating_conditions: tuple[OperatingConditionCandidate, ...]
    requested_evidence: tuple[str, ...]
    open_points: tuple[str, ...]
    boundary_notice: str
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "case_type": self.case_type,
            "damage_patterns": [
                candidate.as_dict() for candidate in self.damage_patterns
            ],
            "operating_conditions": [
                candidate.as_dict() for candidate in self.operating_conditions
            ],
            "requested_evidence": self.requested_evidence,
            "open_points": self.open_points,
            "boundary_notice": self.boundary_notice,
            "event_names": self.event_names,
        }


@dataclass(frozen=True, slots=True)
class ComplaintFailureIntakeBundle:
    schema_version: str
    primary_case_type: str
    artifact_types: tuple[str, ...]
    complaint_intake: ComplaintFailureIntakeArtifact
    failure_analysis_intake: ComplaintFailureIntakeArtifact
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "primary_case_type": self.primary_case_type,
            "artifact_types": self.artifact_types,
            "complaint_intake": self.complaint_intake.as_dict(),
            "failure_analysis_intake": self.failure_analysis_intake.as_dict(),
            "event_names": self.event_names,
        }


class ComplaintFailureIntakeService:
    """Build complaint/failure intake projections without cause decisions."""

    def build(self, payload: str | Mapping[str, Any]) -> ComplaintFailureIntakeBundle:
        text = _payload_to_text(payload)
        primary_case_type = _infer_case_type(payload, text)
        damage_patterns = _extract_damage_patterns(text)
        operating_conditions = _extract_operating_conditions(text)
        evidence_present = _has_evidence_refs(payload)
        requested_evidence = _requested_evidence(evidence_present)
        open_points = _open_points(
            damage_patterns=damage_patterns,
            operating_conditions=operating_conditions,
            evidence_present=evidence_present,
        )

        complaint = ComplaintFailureIntakeArtifact(
            artifact_type=ArtifactType.complaint_intake.value,
            case_type=CaseType.complaint_case.value,
            damage_patterns=damage_patterns,
            operating_conditions=operating_conditions,
            requested_evidence=requested_evidence,
            open_points=open_points,
            boundary_notice=(
                "Reklamations-Intake: Beobachtungen und Betriebsdaten bleiben "
                "Kandidaten bis zur Pruefung."
            ),
            event_names=("ComplaintIntakeCreated",),
        )
        failure = ComplaintFailureIntakeArtifact(
            artifact_type=ArtifactType.failure_analysis_intake.value,
            case_type=CaseType.failure_analysis.value,
            damage_patterns=damage_patterns,
            operating_conditions=operating_conditions,
            requested_evidence=requested_evidence,
            open_points=open_points,
            boundary_notice=(
                "Failure-Intake: Schadensbild wird strukturiert; "
                "die Ursache bleibt offen."
            ),
            event_names=("FailureAnalysisIntakeGenerated",),
        )

        return ComplaintFailureIntakeBundle(
            schema_version=COMPLAINT_FAILURE_SCHEMA_VERSION,
            primary_case_type=primary_case_type,
            artifact_types=COMPLAINT_FAILURE_ARTIFACT_TYPES,
            complaint_intake=complaint,
            failure_analysis_intake=failure,
            event_names=(
                "ComplaintFailureContextCollected",
                "DamagePatternCandidateIdentified",
                "OperatingConditionCandidateExtracted",
                "EvidenceRequestGenerated",
                "ComplaintIntakeCreated",
                "FailureAnalysisIntakeGenerated",
            ),
        )


def build_complaint_failure_intake(
    payload: str | Mapping[str, Any],
) -> ComplaintFailureIntakeBundle:
    return ComplaintFailureIntakeService().build(payload)


def _payload_to_text(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return payload
    values: list[str] = []
    for key in (
        "text",
        "message",
        "description",
        "customer_message",
        "damage_description",
        "failure_description",
    ):
        value = payload.get(key)
        if value:
            values.append(str(value))
    return "\n".join(values)


def _infer_case_type(payload: str | Mapping[str, Any], text: str) -> str:
    if isinstance(payload, Mapping):
        raw = str(payload.get("case_type") or "")
        try:
            case_type = CaseType(raw)
            if case_type in {CaseType.complaint_case, CaseType.failure_analysis}:
                return case_type.value
        except ValueError:
            pass

    normalized = text.casefold()
    if any(token in normalized for token in ("reklamation", "kunde", "leckt wieder")):
        return CaseType.complaint_case.value
    return CaseType.failure_analysis.value


def _extract_damage_patterns(text: str) -> tuple[DamagePatternCandidate, ...]:
    normalized = text.casefold()
    patterns: list[DamagePatternCandidate] = []
    for pattern, triggers in _DAMAGE_PATTERNS:
        if not any(trigger in normalized for trigger in triggers):
            continue
        patterns.append(
            DamagePatternCandidate(
                pattern=pattern,
                label=_damage_label(pattern),
                status="candidate",
                source_type="user_stated",
                evidence_required=True,
            )
        )
    if patterns:
        return tuple(patterns)
    return (
        DamagePatternCandidate(
            pattern="unspecified_damage",
            label="Schadensbild noch unklar",
            status="candidate",
            source_type="user_stated",
            evidence_required=True,
        ),
    )


def _extract_operating_conditions(
    text: str,
) -> tuple[OperatingConditionCandidate, ...]:
    candidates: list[OperatingConditionCandidate] = []
    duration = _DURATION_RE.search(text)
    if duration:
        candidates.append(
            OperatingConditionCandidate(
                field="operating_duration",
                raw_value=f"{duration.group('value')} {duration.group('unit')}",
                status="candidate",
            )
        )
    pressure = _PRESSURE_RE.search(text)
    if pressure:
        candidates.append(
            OperatingConditionCandidate(
                field="pressure",
                raw_value=f"{pressure.group('value')} bar",
                status="candidate",
            )
        )
    temperature = _TEMPERATURE_RE.search(text)
    if temperature:
        candidates.append(
            OperatingConditionCandidate(
                field="temperature",
                raw_value=f"{temperature.group('value')} degC",
                status="candidate",
            )
        )
    rpm = _RPM_RE.search(text)
    if rpm:
        candidates.append(
            OperatingConditionCandidate(
                field="speed",
                raw_value=f"{rpm.group('value')} rpm",
                status="candidate",
            )
        )
    return tuple(candidates)


def _has_evidence_refs(payload: str | Mapping[str, Any]) -> bool:
    if isinstance(payload, str):
        return False
    evidence = payload.get("evidence_refs") or payload.get("documents") or payload.get("photos")
    if evidence is None:
        return False
    if isinstance(evidence, (str, bytes)):
        return bool(evidence)
    if isinstance(evidence, Sequence):
        return bool(evidence)
    return True


def _requested_evidence(evidence_present: bool) -> tuple[str, ...]:
    if evidence_present:
        return ()
    return (
        "Foto der Dichtlippe / Laufspur",
        "Foto der Gegenlaufflaeche",
        "Einbaulage oder Zeichnung",
        "Betriebsdaten zum Zeitpunkt des Ausfalls",
    )


def _open_points(
    *,
    damage_patterns: Sequence[DamagePatternCandidate],
    operating_conditions: Sequence[OperatingConditionCandidate],
    evidence_present: bool,
) -> tuple[str, ...]:
    open_points: list[str] = []
    if not evidence_present:
        open_points.append("damage_evidence")
    if not operating_conditions:
        open_points.append("operating_conditions")
    if any(pattern.pattern == "unspecified_damage" for pattern in damage_patterns):
        open_points.append("damage_pattern")
    open_points.extend(
        (
            "medium_at_failure",
            "installation_context",
            "previous_service_life",
        )
    )
    return tuple(dict.fromkeys(open_points))


def _damage_label(pattern: str) -> str:
    labels = {
        "leakage": "Leckage / Undichtigkeit",
        "premature_failure": "Ausfall nach kurzer Laufzeit",
        "wear": "Verschleissbild",
        "crack_or_break": "Riss oder Bruch",
        "thermal_damage": "thermische Schaedigungsanzeichen",
        "swelling_or_chemical_attack": "Quellung oder chemischer Angriff",
    }
    return labels[pattern]
