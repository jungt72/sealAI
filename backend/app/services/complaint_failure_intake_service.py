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
_SHAFT_DIAMETER_RE = re.compile(
    r"(?:\bWelle\b|\bWellendurchmesser\b|[Øø])\s*(?P<value>\d+(?:[,.]\d+)?)\s*mm\b",
    re.IGNORECASE,
)
_HARDNESS_RE = re.compile(
    r"\b(?P<value>\d+(?:[,.]\d+)?)\s*(?:shore\s*a|sha|sh\s*a|hrc)\b",
    re.IGNORECASE,
)
_ROUGHNESS_RE = re.compile(
    r"\b(?:ra|rz)\s*(?P<value>\d+(?:[,.]\d+)?)\s*(?:um|µm|mikrometer)?\b",
    re.IGNORECASE,
)
_MEDIUM_RE = re.compile(
    r"\b(?:medium\s*(?:ist|=)?|mit|bei)\s+(?P<value>salzwasser|meerwasser|ethanol|wasser|dampf|oel|öl|hydraulikoel|hydrauliköl|getriebeoel|getriebeöl)\b",
    re.IGNORECASE,
)
_DAMAGE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("leakage", ("leckt", "leckage", "undicht", "oelverlust", "verlust")),
    (
        "premature_failure",
        ("ausgefallen", "haelt nur", "nach 3 monaten", "kurzer laufzeit"),
    ),
    ("wear", ("verschleiss", "verschlissen", "abgerieben", "riefen")),
    ("crack_or_break", ("riss", "gerissen", "gebrochen", "bruch")),
    ("thermal_damage", ("verbrannt", "verhaertet", "hart geworden", "ueberhitzt")),
    (
        "swelling_or_chemical_attack",
        ("aufgequollen", "quillt", "chemisch", "angegriffen"),
    ),
    ("extrusion", ("extrusion", "spaltextrusion", "in den spalt", "ausgequetscht")),
    (
        "compression_set",
        (
            "druckverformungsrest",
            "bleibend verformt",
            "plattgedrueckt",
            "plattgedrückt",
        ),
    ),
    ("twisting_or_spiral_damage", ("verdreht", "verdrillt", "spiral", "spiralbruch")),
    (
        "explosive_decompression",
        ("explosive dekompression", "gasdekompression", "blasen", "blister"),
    ),
    (
        "deposits_or_crystallization",
        ("ablagerung", "ablagerungen", "kristall", "verkrustet"),
    ),
    ("corrosion_or_particles", ("korrosion", "rost", "partikel", "sand", "abrasiv")),
)
_SEAL_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rwdr", ("rwdr", "wellendichtring", "radialwellendichtring", "wellendichtung")),
    ("mechanical_seal", ("gleitringdichtung", "glrd", "mechanical seal")),
    ("o_ring", ("o-ring", "oring", "o ring")),
    ("flat_gasket", ("flachdichtung", "dichtungspapier", "flanschdichtung")),
    ("hydraulic_seal", ("hydraulikdichtung", "kolbendichtung", "stangendichtung")),
    ("packing", ("stopfbuchse", "packung", "stopfbuchspackung")),
)
_SAFETY_PATTERNS: tuple[str, ...] = (
    "brennbar",
    "explosiv",
    "atex",
    "giftig",
    "gefahr",
    "heiss",
    "heiß",
    "umwelt",
    "personengefaehrdung",
    "personengefährdung",
)
_LEAK_LOCATION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("shaft_exit", ("welle", "getriebeausgang", "pumpenwelle", "wellenaustritt")),
    ("housing_joint", ("gehaeuse", "gehäuse", "deckel", "flansch")),
    ("seal_lip", ("dichtlippe", "lippe", "laufspur")),
    ("drain_or_quench", ("leckagebohrung", "ablauf", "quench", "sperrraum")),
)
_INSTALLATION_PATTERNS: tuple[str, ...] = (
    "montage",
    "eingebaut",
    "einbau",
    "verkantet",
    "trocken montiert",
    "fett",
    "schmier",
    "werkzeug",
)
_MATERIAL_PATTERNS: tuple[str, ...] = (
    "fkm",
    "nbr",
    "epdm",
    "ptfe",
    "pu",
    "ffkm",
    "vmq",
)
_GEOMETRY_SURFACE_PATTERNS: tuple[str, ...] = (
    "rauheit",
    "ra ",
    "rz ",
    "haerte",
    "härte",
    "rundlauf",
    "exzentr",
    "laufspur",
    "gegenlaufflaeche",
    "gegenlauffläche",
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
class DiagnosticContextCandidate:
    field: str
    raw_value: str
    status: str
    source_type: str = "user_stated"
    evidence_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "raw_value": self.raw_value,
            "status": self.status,
            "source_type": self.source_type,
            "evidence_required": self.evidence_required,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticQuestion:
    field: str
    question: str
    priority: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "question": self.question,
            "priority": self.priority,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ComplaintFailureIntakeArtifact:
    artifact_type: str
    case_type: str
    damage_patterns: tuple[DamagePatternCandidate, ...]
    operating_conditions: tuple[OperatingConditionCandidate, ...]
    diagnostic_context: tuple[DiagnosticContextCandidate, ...]
    requested_evidence: tuple[str, ...]
    open_points: tuple[str, ...]
    diagnostic_questions: tuple[DiagnosticQuestion, ...]
    diagnostic_priority: tuple[str, ...]
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
            "diagnostic_context": [
                candidate.as_dict() for candidate in self.diagnostic_context
            ],
            "requested_evidence": self.requested_evidence,
            "open_points": self.open_points,
            "diagnostic_questions": [
                question.as_dict() for question in self.diagnostic_questions
            ],
            "diagnostic_priority": self.diagnostic_priority,
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
        diagnostic_context = _extract_diagnostic_context(text)
        evidence_present = _has_evidence_refs(payload)
        requested_evidence = _requested_evidence(evidence_present)
        open_points = _open_points(
            damage_patterns=damage_patterns,
            operating_conditions=operating_conditions,
            diagnostic_context=diagnostic_context,
            evidence_present=evidence_present,
        )
        diagnostic_questions = _diagnostic_questions(open_points)

        complaint = ComplaintFailureIntakeArtifact(
            artifact_type=ArtifactType.complaint_intake.value,
            case_type=CaseType.complaint_case.value,
            damage_patterns=damage_patterns,
            operating_conditions=operating_conditions,
            diagnostic_context=diagnostic_context,
            requested_evidence=requested_evidence,
            open_points=open_points,
            diagnostic_questions=diagnostic_questions,
            diagnostic_priority=_DIAGNOSTIC_PRIORITY,
            boundary_notice=(
                "Reklamations-Intake: Beobachtungen und Betriebsdaten bleiben "
                "Kandidaten bis zur Prüfung. Eine Ursache wird nicht final bestätigt."
            ),
            event_names=("ComplaintIntakeCreated",),
        )
        failure = ComplaintFailureIntakeArtifact(
            artifact_type=ArtifactType.failure_analysis_intake.value,
            case_type=CaseType.failure_analysis.value,
            damage_patterns=damage_patterns,
            operating_conditions=operating_conditions,
            diagnostic_context=diagnostic_context,
            requested_evidence=requested_evidence,
            open_points=open_points,
            diagnostic_questions=diagnostic_questions,
            diagnostic_priority=_DIAGNOSTIC_PRIORITY,
            boundary_notice=(
                "Failure-Intake: Schadensbild wird strukturiert; "
                "die Ursache bleibt offen, bis Befund, Betriebsdaten und Evidence geprüft sind."
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
                "DiagnosticContextCandidateExtracted",
                "EvidenceRequestGenerated",
                "DiagnosticQuestionGenerated",
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


def _extract_diagnostic_context(text: str) -> tuple[DiagnosticContextCandidate, ...]:
    normalized = text.casefold()
    candidates: list[DiagnosticContextCandidate] = []
    if any(token in normalized for token in _SAFETY_PATTERNS):
        candidates.append(
            DiagnosticContextCandidate(
                field="safety_context",
                raw_value="safety_or_compliance_relevance_mentioned",
                status="candidate",
                evidence_required=True,
            )
        )
    for value, triggers in _SEAL_TYPE_PATTERNS:
        if any(trigger in normalized for trigger in triggers):
            candidates.append(
                DiagnosticContextCandidate(
                    field="seal_type",
                    raw_value=value,
                    status="candidate",
                    evidence_required=True,
                )
            )
            break
    for value, triggers in _LEAK_LOCATION_PATTERNS:
        if any(trigger in normalized for trigger in triggers):
            candidates.append(
                DiagnosticContextCandidate(
                    field="leak_location",
                    raw_value=value,
                    status="candidate",
                    evidence_required=True,
                )
            )
            break
    medium = _MEDIUM_RE.search(text)
    if medium:
        candidates.append(
            DiagnosticContextCandidate(
                field="medium_at_failure",
                raw_value=medium.group("value"),
                status="candidate",
            )
        )
    if any(token in normalized for token in _INSTALLATION_PATTERNS):
        candidates.append(
            DiagnosticContextCandidate(
                field="installation_context",
                raw_value="installation_or_assembly_context_mentioned",
                status="candidate",
                evidence_required=True,
            )
        )
    material = _first_token(normalized, _MATERIAL_PATTERNS)
    if material:
        candidates.append(
            DiagnosticContextCandidate(
                field="material_or_compound",
                raw_value=material.upper(),
                status="candidate",
                evidence_required=True,
            )
        )
    if any(
        token in normalized for token in _GEOMETRY_SURFACE_PATTERNS
    ) or _SHAFT_DIAMETER_RE.search(text):
        candidates.append(
            DiagnosticContextCandidate(
                field="geometry_surface_context",
                raw_value="geometry_or_counterface_context_mentioned",
                status="candidate",
                evidence_required=True,
            )
        )
    shaft_diameter = _SHAFT_DIAMETER_RE.search(text)
    if shaft_diameter:
        candidates.append(
            DiagnosticContextCandidate(
                field="shaft_diameter",
                raw_value=f"{shaft_diameter.group('value')} mm",
                status="candidate",
            )
        )
    hardness = _HARDNESS_RE.search(text)
    if hardness:
        candidates.append(
            DiagnosticContextCandidate(
                field="hardness",
                raw_value=hardness.group(0),
                status="candidate",
            )
        )
    roughness = _ROUGHNESS_RE.search(text)
    if roughness:
        candidates.append(
            DiagnosticContextCandidate(
                field="surface_roughness",
                raw_value=roughness.group(0),
                status="candidate",
            )
        )
    return tuple(candidates)


def _has_evidence_refs(payload: str | Mapping[str, Any]) -> bool:
    if isinstance(payload, str):
        return False
    evidence = (
        payload.get("evidence_refs")
        or payload.get("documents")
        or payload.get("photos")
    )
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
        "Fotos im ungewaschenen Originalzustand",
        "Foto der Dichtlippe / Laufspur",
        "Foto der Gegenlauffläche",
        "Einbaulage oder Zeichnung",
        "Betriebsdaten zum Zeitpunkt des Ausfalls",
    )


def _open_points(
    *,
    damage_patterns: Sequence[DamagePatternCandidate],
    operating_conditions: Sequence[OperatingConditionCandidate],
    diagnostic_context: Sequence[DiagnosticContextCandidate],
    evidence_present: bool,
) -> tuple[str, ...]:
    present_fields = {candidate.field for candidate in diagnostic_context} | {
        condition.field for condition in operating_conditions
    }
    present_fields |= {
        mapped
        for condition in operating_conditions
        for mapped in _OPERATING_FIELD_EQUIVALENTS.get(condition.field, ())
    }
    open_points: list[str] = []
    if "safety_context" not in present_fields:
        open_points.append("safety_context")
    if "leak_location" not in present_fields:
        open_points.append("leak_location")
    if not evidence_present:
        open_points.append("damage_evidence")
    if "seal_type" not in present_fields:
        open_points.append("seal_type")
    if not operating_conditions:
        open_points.append("operating_conditions")
    if any(pattern.pattern == "unspecified_damage" for pattern in damage_patterns):
        open_points.append("damage_pattern")
    for field in _DIAGNOSTIC_PRIORITY:
        if field in _FIELDS_INFERRED_FROM_DAMAGE:
            continue
        if field not in present_fields and field not in open_points:
            open_points.append(field)
    return tuple(dict.fromkeys(open_points))


_DIAGNOSTIC_PRIORITY: tuple[str, ...] = (
    "safety_context",
    "leak_location",
    "damage_evidence",
    "seal_type",
    "failure_timing",
    "damage_pattern",
    "operating_conditions",
    "medium_at_failure",
    "pressure_profile",
    "temperature_at_seal",
    "motion_profile",
    "geometry_surface_context",
    "installation_context",
    "material_or_compound",
    "previous_service_life",
)
_OPERATING_FIELD_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "operating_duration": ("failure_timing", "previous_service_life"),
    "pressure": ("pressure_profile",),
    "temperature": ("temperature_at_seal",),
    "speed": ("motion_profile",),
}
_FIELDS_INFERRED_FROM_DAMAGE = frozenset({"damage_pattern"})
_QUESTION_TEXT: dict[str, tuple[str, str]] = {
    "safety_context": (
        "Gibt es Sicherheits-, Umwelt-, Brand-, ATEX- oder Personengefährdung im Zusammenhang mit der Leckage?",
        "Sicherheit und Anlagenzustand müssen vor jeder technischen Ursachenlogik geklärt sein.",
    ),
    "leak_location": (
        "Wo genau tritt die Leckage auf: an der Welle, am Gehäuse, an der Dichtlippe oder an einer Entlastungs-/Leckagebohrung?",
        "Die Leckstelle trennt Dichtungsversagen, Einbauproblem und Nebensysteme.",
    ),
    "damage_evidence": (
        "Gibt es Fotos im ungewaschenen Originalzustand von Dichtung, Laufspur, Gegenfläche und Einbaulage?",
        "Der Originalbefund verhindert, dass wichtige Spuren durch Reinigung oder Demontage verloren gehen.",
    ),
    "seal_type": (
        "Um welchen Dichtungstyp geht es, zum Beispiel RWDR, O-Ring, Flachdichtung, Hydraulikdichtung oder Gleitringdichtung?",
        "Der Dichtungstyp bestimmt, welche Schadensmechanismen und Pflichtdaten relevant sind.",
    ),
    "failure_timing": (
        "Wann tritt die Leckage auf: sofort nach Montage, beim Anfahren, im Dauerlauf, nach Druckspitzen oder erst nach bestimmter Laufzeit?",
        "Der Zeitpunkt ist ein starker Hinweis auf Montage, Betrieb, Werkstoff oder Verschleißmechanismus.",
    ),
    "damage_pattern": (
        "Welches Schadensbild ist sichtbar: Verschleiß, Risse, Quellung, Verhärtung, Extrusion, Ablagerungen oder Verdrehung?",
        "Das Schadensbild liefert Hypothesen, ersetzt aber keine gesicherte Ursachenprüfung.",
    ),
    "operating_conditions": (
        "Welche Betriebsdaten galten beim Ausfall: Medium, Druck, Temperatur, Drehzahl oder Hub, Laufzeit und Lastwechsel?",
        "Die reale Belastung am Ausfallzeitpunkt ist wichtiger als nur die nominalen Katalogdaten.",
    ),
    "medium_at_failure": (
        "Welches Medium lag direkt an der Dichtstelle an, inklusive Konzentration, Additiven, Wasseranteil, Gasanteil oder Reinigungsmedien?",
        "Chemische und abrasive Einflüsse lassen sich ohne das echte Medium nicht seriös einordnen.",
    ),
    "pressure_profile": (
        "Gab es Druckspitzen, Pulsation, Vakuum, schnelle Entlastung oder wechselnde Druckrichtung?",
        "Druckprofile erklären häufig Extrusion, Umstülpen, Gasdekompression oder instabile Dichtbedingungen.",
    ),
    "temperature_at_seal": (
        "Welche Temperatur lag direkt an der Dichtstelle an, nicht nur im Behälter oder in der Rohrleitung?",
        "Die Dichtstellentemperatur bestimmt Alterung, Medienzustand und Werkstoffgrenzen.",
    ),
    "motion_profile": (
        "Welche Bewegung lag an: Drehzahl, Hub, Schwenkbewegung, Start-Stopp-Betrieb oder längere Stillstände?",
        "Bewegung und Stillstand beeinflussen Reibung, Schmierung, Trockenlauf und Verschleiß.",
    ),
    "geometry_surface_context": (
        "Welche Maße und Gegenlaufdaten sind bekannt: Welle, Bohrung, Einbaubreite, Rauheit, Härte, Rundlauf und Exzentrizität?",
        "Geometrie und Oberfläche entscheiden, ob ein Schadensbild aus Betrieb oder Einbauraum plausibel wird.",
    ),
    "installation_context": (
        "Wie wurde montiert: Werkzeug, Schmierung, Einbaurichtung, Kanten, Fasen, Schutz der Dichtlippe und Montagehistorie?",
        "Montagefehler können wie Material- oder Betriebsprobleme aussehen.",
    ),
    "material_or_compound": (
        "Welche Werkstoff-, Compound- oder Härteangabe ist belegt?",
        "Werkstoffnamen ohne Beleg sind nur Kandidaten für die Herstellerprüfung.",
    ),
    "previous_service_life": (
        "Wie lange hielt die vorherige Lösung unter vergleichbaren Bedingungen?",
        "Die Standzeit-Historie trennt Einzelfehler von systematischer Überlastung.",
    ),
}


def _diagnostic_questions(open_points: Sequence[str]) -> tuple[DiagnosticQuestion, ...]:
    questions: list[DiagnosticQuestion] = []
    for field in _DIAGNOSTIC_PRIORITY:
        if field not in open_points:
            continue
        question_meta = _QUESTION_TEXT.get(field)
        if question_meta is None:
            continue
        question, reason = question_meta
        questions.append(
            DiagnosticQuestion(
                field=field,
                question=question,
                priority=len(questions) + 1,
                reason=reason,
            )
        )
        if len(questions) >= 5:
            break
    return tuple(questions)


def _damage_label(pattern: str) -> str:
    labels = {
        "leakage": "Leckage / Undichtigkeit",
        "premature_failure": "Ausfall nach kurzer Laufzeit",
        "wear": "Verschleißbild",
        "crack_or_break": "Riss oder Bruch",
        "thermal_damage": "thermische Schädigungsanzeichen",
        "swelling_or_chemical_attack": "Quellung oder chemischer Angriff",
        "extrusion": "Extrusion / Spaltpressung",
        "compression_set": "bleibende Verformung",
        "twisting_or_spiral_damage": "Verdrehung / Spiralschaden",
        "explosive_decompression": "Gasdekompression / Blasenbildung",
        "deposits_or_crystallization": "Ablagerung / Kristallisation",
        "corrosion_or_particles": "Korrosion / Partikelbelastung",
    }
    return labels[pattern]


def _first_token(text: str, tokens: Sequence[str]) -> str | None:
    for token in tokens:
        if re.search(rf"\b{re.escape(token)}\b", text, re.IGNORECASE):
            return token
    return None
