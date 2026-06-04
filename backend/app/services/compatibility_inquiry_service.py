from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.domain.artifact_type import ArtifactType
from app.domain.case_type import CaseType


COMPATIBILITY_INQUIRY_SCHEMA_VERSION = "compatibility_inquiry_v0.8.3"
COMPATIBILITY_INQUIRY_ARTIFACT_TYPES: tuple[str, ...] = (
    ArtifactType.technical_inquiry_summary.value,
    ArtifactType.compatibility_matrix.value,
)
COMPATIBILITY_INQUIRY_CASE_TYPE = CaseType.compatibility_inquiry.value

_DIMENSION_RE = re.compile(
    r"\b(?P<shaft>\d{1,4}(?:[,.]\d+)?)\s*[xX*]\s*"
    r"(?P<bore>\d{1,4}(?:[,.]\d+)?)\s*[xX*]\s*"
    r"(?P<width>\d{1,4}(?:[,.]\d+)?)\b"
)
_DIN_RE = re.compile(r"\bDIN\s*(?P<number>\d{3,5})\b", re.IGNORECASE)
_VALUE_RE_TEMPLATE = (
    r"\b{term}\b\s*(?:[:=]|liegt bei|von|mit)?\s*"
    r"(?P<value>\d+(?:[,.]\d+)?)?\s*(?P<unit>[A-Za-z/%]+)?"
)
_METHOD_WORDS = ("methode", "verfahren", "analyse", "pruef", "pruf", "test")
_MATERIAL_ALIASES: dict[str, str] = {
    "fkm": "FKM",
    "ptfe": "PTFE",
    "nbr": "NBR",
    "epdm": "EPDM",
    "ffkm": "FFKM",
}
_COMPLIANCE_FLAGS: dict[str, str] = {
    "fda": "FDA",
    "1935/2004": "EU 1935/2004",
    "eu 10/2011": "EU 10/2011",
    "atex": "ATEX",
    "ta-luft": "TA-Luft",
    "ta luft": "TA-Luft",
}
_LAB_TERMS: tuple[str, ...] = (
    "wasser",
    "natrium",
    "kalium",
    "chlorid",
    "ph",
)


@dataclass(frozen=True, slots=True)
class ProductDesignation:
    raw_text: str
    designation: str | None
    seal_type: str | None
    dimensions: dict[str, float] | None
    norm_refs: tuple[str, ...]
    material_family: str | None
    compliance_flags: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "designation": self.designation,
            "seal_type": self.seal_type,
            "dimensions": self.dimensions,
            "norm_refs": self.norm_refs,
            "material_family": self.material_family,
            "compliance_flags": self.compliance_flags,
        }


@dataclass(frozen=True, slots=True)
class LabValueCandidate:
    analyte: str
    raw_value: str | None
    numeric_value: float | None
    unit: str | None
    status: str
    missing: tuple[str, ...]
    source: str = "user_text"

    @property
    def review_required(self) -> bool:
        return bool(self.missing) or self.status != "candidate"

    def as_dict(self) -> dict[str, Any]:
        return {
            "analyte": self.analyte,
            "raw_value": self.raw_value,
            "numeric_value": self.numeric_value,
            "unit": self.unit,
            "status": self.status,
            "missing": self.missing,
            "source": self.source,
            "review_required": self.review_required,
        }


@dataclass(frozen=True, slots=True)
class CompatibilityMatrixItem:
    topic: str
    status: str
    reason: str
    open_points: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "status": self.status,
            "reason": self.reason,
            "open_points": self.open_points,
        }


@dataclass(frozen=True, slots=True)
class CompatibilityInquiryArtifact:
    schema_version: str
    case_type: str
    artifact_types: tuple[str, ...]
    product_designation: ProductDesignation
    lab_value_candidates: tuple[LabValueCandidate, ...]
    missing_values: tuple[str, ...]
    compatibility_matrix: tuple[CompatibilityMatrixItem, ...]
    technical_inquiry_summary: tuple[str, ...]
    boundary_notice: str
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_type": self.case_type,
            "artifact_types": self.artifact_types,
            "product_designation": self.product_designation.as_dict(),
            "lab_value_candidates": [
                candidate.as_dict() for candidate in self.lab_value_candidates
            ],
            "missing_values": self.missing_values,
            "compatibility_matrix": [
                item.as_dict() for item in self.compatibility_matrix
            ],
            "technical_inquiry_summary": self.technical_inquiry_summary,
            "boundary_notice": self.boundary_notice,
            "event_names": self.event_names,
        }


class CompatibilityInquiryService:
    """Build read-only compatibility inquiry artifacts from case text.

    The service is deliberately conservative: detected product labels and lab
    values remain inquiry facts or candidates. It does not decide material
    compatibility and does not create backend truth.
    """

    def build(self, payload: str | Mapping[str, Any]) -> CompatibilityInquiryArtifact:
        text = _payload_to_text(payload)
        product = _extract_product_designation(text)
        lab_candidates = _extract_lab_value_candidates(text)
        missing_values = _missing_values(product, lab_candidates)
        matrix = _build_matrix(product, lab_candidates, missing_values)
        summary = _build_summary(product, lab_candidates, missing_values)

        return CompatibilityInquiryArtifact(
            schema_version=COMPATIBILITY_INQUIRY_SCHEMA_VERSION,
            case_type=COMPATIBILITY_INQUIRY_CASE_TYPE,
            artifact_types=COMPATIBILITY_INQUIRY_ARTIFACT_TYPES,
            product_designation=product,
            lab_value_candidates=lab_candidates,
            missing_values=missing_values,
            compatibility_matrix=matrix,
            technical_inquiry_summary=summary,
            boundary_notice=(
                "Diese Anfrage ist eine strukturierte Pruefgrundlage. "
                "Werkstoff-, Medium- und Grenzwertfragen benoetigen eine "
                "Hersteller- oder Compoundpruefung."
            ),
            event_names=(
                "CompatibilityInquiryClassified",
                "ProductDesignationExtracted",
                "LabValuesMarkedAsCandidates",
                "MissingCompatibilityInputsIdentified",
                "CompatibilityMatrixDerived",
                "TechnicalInquirySummaryDerived",
            ),
        )


def build_compatibility_inquiry_artifact(
    payload: str | Mapping[str, Any],
) -> CompatibilityInquiryArtifact:
    return CompatibilityInquiryService().build(payload)


def _payload_to_text(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return payload
    fields: list[str] = []
    for key in (
        "text",
        "message",
        "user_message",
        "raw_text",
        "description",
        "product_designation",
        "lab_report",
    ):
        value = payload.get(key)
        if value:
            fields.append(str(value))
    return "\n".join(fields)


def _extract_product_designation(text: str) -> ProductDesignation:
    normalized = text.casefold()
    designation = _extract_designation(text)
    dimensions = _extract_dimensions(text)
    seal_type = (
        "radial_shaft_seal" if _contains_any(normalized, ("wdr", "rwdr")) else None
    )
    material = _extract_material(normalized)
    norms = tuple(f"DIN {match.group('number')}" for match in _DIN_RE.finditer(text))
    compliance_flags = tuple(
        label for token, label in _COMPLIANCE_FLAGS.items() if token in normalized
    )
    return ProductDesignation(
        raw_text=text,
        designation=designation,
        seal_type=seal_type,
        dimensions=dimensions,
        norm_refs=norms,
        material_family=material,
        compliance_flags=compliance_flags,
    )


def _extract_designation(text: str) -> str | None:
    dimension = _DIMENSION_RE.search(text)
    if not dimension:
        return None

    start = max(0, dimension.start() - 12)
    end = min(len(text), dimension.end() + 28)
    snippet = text[start:end]
    words = re.findall(r"[A-Za-z0-9/.-]+", snippet)
    if not words:
        return dimension.group(0)

    relevant: list[str] = []
    keep_next = False
    for word in words:
        word_key = word.casefold()
        if word_key in {"wdr", "rwdr", "as"}:
            relevant.append(word.upper())
            keep_next = True
            continue
        if word_key in _MATERIAL_ALIASES:
            relevant.append(word.upper())
            keep_next = False
            continue
        if _DIN_RE.fullmatch(word) or word_key == "din":
            relevant.append(word.upper())
            keep_next = True
            continue
        if _DIMENSION_RE.fullmatch(word) or re.fullmatch(
            r"\d{1,4}[xX]\d{1,4}[xX]\d{1,4}", word
        ):
            relevant.append(word)
            keep_next = True
            continue
        if keep_next and word_key.isdigit():
            relevant.append(word)
            keep_next = False
            continue
        if word_key in {"fda", "atex"}:
            relevant.append(word.upper())
            keep_next = False
    return " ".join(relevant) or dimension.group(0)


def _extract_dimensions(text: str) -> dict[str, float] | None:
    match = _DIMENSION_RE.search(text)
    if not match:
        return None
    return {
        "shaft_diameter_mm": _to_float(match.group("shaft")),
        "housing_bore_mm": _to_float(match.group("bore")),
        "width_mm": _to_float(match.group("width")),
    }


def _extract_material(normalized_text: str) -> str | None:
    for token, material in _MATERIAL_ALIASES.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized_text):
            return material
    return None


def _extract_lab_value_candidates(text: str) -> tuple[LabValueCandidate, ...]:
    normalized = text.casefold()
    candidates: list[LabValueCandidate] = []
    method_present = any(word in normalized for word in _METHOD_WORDS)
    for term in _LAB_TERMS:
        match = re.search(
            _VALUE_RE_TEMPLATE.format(term=re.escape(term)),
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        raw_value = match.group("value")
        unit = match.group("unit") if raw_value else None
        missing = _candidate_missing(
            raw_value=raw_value,
            unit=unit,
            method_present=method_present,
        )
        status = (
            "candidate"
            if raw_value and unit and method_present
            else "candidate_incomplete"
        )
        candidates.append(
            LabValueCandidate(
                analyte=_label_for_lab_term(term),
                raw_value=raw_value,
                numeric_value=_to_float(raw_value) if raw_value else None,
                unit=unit,
                status=status,
                missing=missing,
            )
        )
    return tuple(candidates)


def _candidate_missing(
    *,
    raw_value: str | None,
    unit: str | None,
    method_present: bool,
) -> tuple[str, ...]:
    missing: list[str] = []
    if not raw_value:
        missing.append("value")
    if not unit:
        missing.append("unit")
    if not method_present:
        missing.append("method")
    return tuple(missing)


def _missing_values(
    product: ProductDesignation,
    lab_candidates: Sequence[LabValueCandidate],
) -> tuple[str, ...]:
    missing: list[str] = []
    if not product.designation:
        missing.append("product_designation")
    if not product.material_family:
        missing.append("material_family")
    if not product.dimensions:
        missing.append("dimensions")
    if not lab_candidates:
        missing.append("lab_values")
    for candidate in lab_candidates:
        for field in candidate.missing:
            missing.append(f"{candidate.analyte}.{field}")
    return tuple(dict.fromkeys(missing))


def _build_matrix(
    product: ProductDesignation,
    lab_candidates: Sequence[LabValueCandidate],
    missing_values: Sequence[str],
) -> tuple[CompatibilityMatrixItem, ...]:
    return (
        CompatibilityMatrixItem(
            topic="Produktbezeichnung",
            status="candidate" if product.designation else "missing",
            reason=(
                "Dichtungsbezeichnung wurde als Anfragekontext erkannt."
                if product.designation
                else "Keine eindeutige Dichtungsbezeichnung erkannt."
            ),
            open_points=_open_points_from_missing(
                missing_values,
                ("product_designation", "dimensions", "material_family"),
            ),
        ),
        CompatibilityMatrixItem(
            topic="Laborwerte / Mediumbericht",
            status="review_required" if lab_candidates else "missing",
            reason=(
                "Laborwerte sind pruefungsrelevant und bleiben Kandidaten."
                if lab_candidates
                else "Keine Laborwerte im Anfragekontext erkannt."
            ),
            open_points=tuple(
                value
                for value in missing_values
                if "." in value or value == "lab_values"
            ),
        ),
        CompatibilityMatrixItem(
            topic="Werkstoff- und Compoundpruefung",
            status="review_required",
            reason=(
                "Materialfamilie und Medienbericht reichen ohne Herstellerdaten "
                "nicht fuer eine technische Bestaetigung."
            ),
            open_points=(
                "exakte Compoundbezeichnung",
                "Grenzwerte des Herstellers",
                "Betriebstemperatur und Kontaktzeit",
            ),
        ),
        CompatibilityMatrixItem(
            topic="Nachweise / Compliance-Kontext",
            status="review_required" if product.compliance_flags else "open",
            reason=(
                "Erkannte Nachweisbegriffe muessen als Anforderungen an den "
                "Hersteller gegeben werden."
                if product.compliance_flags
                else "Falls Nachweise relevant sind, muessen sie explizit benannt werden."
            ),
            open_points=tuple(product.compliance_flags) or ("benoetigte Nachweise",),
        ),
    )


def _build_summary(
    product: ProductDesignation,
    lab_candidates: Sequence[LabValueCandidate],
    missing_values: Sequence[str],
) -> tuple[str, ...]:
    product_line = (
        f"Anfragekontext: {product.designation}."
        if product.designation
        else "Anfragekontext: Dichtungsbezeichnung noch offen."
    )
    material_line = (
        f"Werkstofffamilie als Kandidat: {product.material_family}."
        if product.material_family
        else "Werkstofffamilie muss fuer die Anfrage geklaert werden."
    )
    lab_line = (
        "Pruefungsrelevante Laborwerte: "
        + ", ".join(candidate.analyte for candidate in lab_candidates)
        + "."
        if lab_candidates
        else "Laborwerte oder Medienbericht fehlen noch."
    )
    missing_line = (
        "Offene Angaben: " + ", ".join(missing_values) + "."
        if missing_values
        else "Offene Angaben: keine aus diesem Text erkannt."
    )
    return (
        product_line,
        material_line,
        lab_line,
        missing_line,
        "Ergebnisgrenze: keine technische Bestaetigung; "
        "Hersteller- oder Compoundpruefung erforderlich.",
    )


def _open_points_from_missing(
    missing_values: Sequence[str],
    keys: Sequence[str],
) -> tuple[str, ...]:
    return tuple(value for value in missing_values if value in set(keys))


def _contains_any(text: str, tokens: Sequence[str]) -> bool:
    return any(re.search(rf"\b{re.escape(token)}\b", text) for token in tokens)


def _label_for_lab_term(term: str) -> str:
    labels = {
        "wasser": "Wasser",
        "natrium": "Natrium",
        "kalium": "Kalium",
        "chlorid": "Chlorid",
        "ph": "pH",
    }
    return labels[term]


def _to_float(value: str) -> float:
    return float(value.replace(",", "."))
