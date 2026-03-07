from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping


CANDIDATE_SPECIFICITY_VALUES = (
    "compound_specific",
    "family_level",
    "material_class",
    "document_hit",
    "unresolved",
)

_MATERIAL_FAMILY_CODES = {
    "PTFE",
    "TFM",
    "FKM",
    "FFKM",
    "NBR",
    "HNBR",
    "EPDM",
    "VMQ",
    "MVQ",
    "PU",
    "PUR",
    "PEEK",
    "POM",
    "PA",
    "UHMWPE",
    "ETFE",
    "PCTFE",
}
_GENERIC_MATERIAL_TERMS = {
    "material",
    "werkstoff",
    "elastomer",
    "polymer",
    "kunststoff",
    "plastic",
    "rubber",
    "compound",
    "family",
    "familie",
}
_NORMALIZED_GENERIC_MATERIAL_TERMS = {re.sub(r"[^a-z0-9]+", "", item.lower()) for item in _GENERIC_MATERIAL_TERMS}


def _normalize_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _material_token_kind(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "unresolved"
    upper = raw.upper()
    if upper in _MATERIAL_FAMILY_CODES:
        return "family_level"
    token = _normalize_token(raw)
    if token in _NORMALIZED_GENERIC_MATERIAL_TERMS:
        return "material_class"
    return "compound_specific"


def infer_candidate_specificity(
    *,
    kind: str,
    value: Any,
    identity_class: str | None = None,
    source_kind: str | None = None,
) -> str:
    normalized_identity = str(identity_class or "").strip().lower()
    normalized_source = str(source_kind or "").strip().lower()

    if normalized_source == "retrieval":
        return "document_hit"

    if kind == "material":
        material_kind = _material_token_kind(value)
        if normalized_identity == "confirmed":
            return material_kind
        if normalized_identity == "family_only":
            return "family_level"
        if normalized_identity == "probable":
            return "material_class" if material_kind == "material_class" else "unresolved"
        if normalized_identity == "unresolved":
            return "unresolved"
        if normalized_source == "heuristic":
            return "family_level" if material_kind in {"family_level", "compound_specific"} else material_kind
        return material_kind if material_kind != "compound_specific" else "unresolved"

    if kind in {"trade_name", "product", "product_name"}:
        if normalized_identity == "confirmed":
            return "compound_specific"
        return "unresolved"

    if normalized_identity == "confirmed":
        return "compound_specific"
    return "unresolved"


def annotate_material_choice(
    choice: Mapping[str, Any] | None,
    *,
    identity_map: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    annotated = dict(choice or {})
    material = str(annotated.get("material") or "").strip()
    confidence = str(annotated.get("confidence") or "").strip().lower()
    source_kind = str(annotated.get("source_kind") or "").strip().lower()
    if not source_kind:
        if confidence == "retrieved":
            source_kind = "retrieval"
        elif confidence == "heuristic":
            source_kind = "heuristic"
        elif confidence in {"user", "asserted"}:
            source_kind = confidence
        else:
            source_kind = "unknown"

    identity_meta = dict((identity_map or {}).get("material") or {})
    raw_identity_class = str(annotated.get("identity_class") or identity_meta.get("identity_class") or "").strip().lower()
    inferred_identity_class = raw_identity_class or None

    specificity = str(annotated.get("specificity") or "").strip().lower()
    if specificity not in CANDIDATE_SPECIFICITY_VALUES:
        specificity = infer_candidate_specificity(
            kind="material",
            value=material,
            identity_class=inferred_identity_class,
            source_kind=source_kind,
        )

    annotated["source_kind"] = source_kind
    annotated["identity_class"] = raw_identity_class or "unresolved"
    annotated["specificity"] = specificity
    annotated["governed"] = bool(
        annotated.get("governed")
        if "governed" in annotated
        else (source_kind in {"user", "asserted"} and (raw_identity_class or "unresolved") == "confirmed" and specificity == "compound_specific")
    )
    return annotated


def build_candidate_clusters(
    candidates: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Classify candidates into the three Blueprint clusters deterministically.

    Primary signal: ``excluded_by_gate`` field set by chemical_resistance or
    material_limits deterministic checks — no keyword matching on rationale text.

    Secondary signal (for non-excluded candidates): ``governed`` + ``specificity``
    determine whether a candidate is ready to present or still needs manufacturer
    validation.

    Returns:
        Dict with keys:
        - ``plausibly_viable``: governed=True and specificity==compound_specific
        - ``viable_only_with_manufacturer_validation``: present but not compound-confirmed
        - ``inadmissible_or_excluded``: deterministically excluded by a gate check
    """
    plausibly_viable: List[Dict[str, Any]] = []
    viable_only: List[Dict[str, Any]] = []
    inadmissible: List[Dict[str, Any]] = []

    for candidate in candidates:
        if candidate.get("excluded_by_gate"):
            inadmissible.append(candidate)
            continue
        if bool(candidate.get("governed")) and str(candidate.get("specificity") or "") == "compound_specific":
            plausibly_viable.append(candidate)
        else:
            viable_only.append(candidate)

    return {
        "plausibly_viable": plausibly_viable,
        "viable_only_with_manufacturer_validation": viable_only,
        "inadmissible_or_excluded": inadmissible,
    }


__all__ = [
    "CANDIDATE_SPECIFICITY_VALUES",
    "annotate_material_choice",
    "build_candidate_clusters",
    "infer_candidate_specificity",
]
