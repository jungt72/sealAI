from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping


from app.langgraph_v2.state.governance_types import IdentityClass, SpecificityLevel


CANDIDATE_SPECIFICITY_VALUES = (
    SpecificityLevel.COMPOUND_REQUIRED.value,
    SpecificityLevel.PRODUCT_FAMILY_REQUIRED.value,
    SpecificityLevel.SUBFAMILY.value,
    SpecificityLevel.FAMILY_ONLY.value,
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


def _material_token_kind(value: Any) -> SpecificityLevel:
    raw = str(value or "").strip()
    if not raw:
        return SpecificityLevel.FAMILY_ONLY
    upper = raw.upper()
    if upper in _MATERIAL_FAMILY_CODES:
        return SpecificityLevel.FAMILY_ONLY
    token = _normalize_token(raw)
    if token in _NORMALIZED_GENERIC_MATERIAL_TERMS:
        return SpecificityLevel.PRODUCT_FAMILY_REQUIRED
    return SpecificityLevel.COMPOUND_REQUIRED


_SPECIFICITY_RANK = {
    SpecificityLevel.COMPOUND_REQUIRED.value: 3,
    SpecificityLevel.PRODUCT_FAMILY_REQUIRED.value: 2,
    SpecificityLevel.SUBFAMILY.value: 1,
    SpecificityLevel.FAMILY_ONLY.value: 0,
}


def get_specificity_rank(specificity: str | None) -> int:
    """Return numeric rank for a specificity level (higher is more specific)."""
    return _SPECIFICITY_RANK.get(str(specificity or "").strip().lower(), 0)


def infer_candidate_specificity(
    *,
    kind: str,
    value: Any,
    identity_class: str | None = None,
    source_kind: str | None = None,
) -> str:
    # Use central normalization for identity_class
    normalized_identity = IdentityClass.normalize(identity_class)
    normalized_source = str(source_kind or "").strip().lower()

    if normalized_source == "retrieval":
        return SpecificityLevel.FAMILY_ONLY.value

    if kind == "material":
        material_kind = _material_token_kind(value)
        if normalized_identity == IdentityClass.CONFIRMED:
            return material_kind.value
        if normalized_identity == IdentityClass.FAMILY_ONLY:
            return SpecificityLevel.FAMILY_ONLY.value
        if normalized_identity == IdentityClass.PROBABLE:
            # Probable identity only allows family-level specificity in v1.2
            return SpecificityLevel.PRODUCT_FAMILY_REQUIRED.value if material_kind == SpecificityLevel.PRODUCT_FAMILY_REQUIRED else SpecificityLevel.FAMILY_ONLY.value
        if normalized_identity == IdentityClass.UNRESOLVED:
            return SpecificityLevel.FAMILY_ONLY.value
        if normalized_source == "heuristic":
            # Heuristic material identification is never better than family_only in v1.2
            return SpecificityLevel.FAMILY_ONLY.value
        return material_kind.value if material_kind != SpecificityLevel.COMPOUND_REQUIRED else SpecificityLevel.FAMILY_ONLY.value

    if kind in {"trade_name", "product", "product_name"}:
        if normalized_identity == IdentityClass.CONFIRMED:
            return SpecificityLevel.COMPOUND_REQUIRED.value
        return SpecificityLevel.FAMILY_ONLY.value

    if normalized_identity == IdentityClass.CONFIRMED:
        return SpecificityLevel.COMPOUND_REQUIRED.value
    return SpecificityLevel.FAMILY_ONLY.value


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
    # Use central normalization
    identity_class_obj = IdentityClass.normalize(annotated.get("identity_class") or identity_meta.get("identity_class"))
    raw_identity_class = identity_class_obj.value

    specificity = str(annotated.get("specificity") or "").strip().lower()
    if specificity not in CANDIDATE_SPECIFICITY_VALUES:
        specificity = infer_candidate_specificity(
            kind="material",
            value=material,
            identity_class=raw_identity_class,
            source_kind=source_kind,
        )

    annotated["source_kind"] = source_kind
    annotated["identity_class"] = raw_identity_class
    annotated["specificity"] = specificity
    
    # Blueprint v1.2: A candidate is governed if it comes from an authoritative source
    # (user or asserted) and has a confirmed identity.
    # We no longer hard-code compound_required here; family assertions are also governed.
    is_authoritative = source_kind in {"user", "asserted"}
    is_confirmed = identity_class_obj == IdentityClass.CONFIRMED
    
    annotated["governed"] = bool(
        annotated.get("governed")
        if "governed" in annotated
        else (is_authoritative and is_confirmed)
    )
    return annotated


def build_candidate_clusters(
    candidates: List[Dict[str, Any]],
    *,
    required_specificity: str | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Classify candidates into the three Blueprint clusters deterministically.

    Primary signal: ``excluded_by_gate`` field set by chemical_resistance or
    material_limits deterministic checks — no keyword matching on rationale text.

    Secondary signal (for non-excluded candidates): ``governed`` + ``specificity``
    determine whether a candidate is ready to present or still needs manufacturer
    validation.

    Returns:
        Dict with keys:
        - ``plausibly_viable``: governed=True and meets specificity requirements
        - ``viable_only_with_manufacturer_validation``: technically okay but needs confirmation
        - ``inadmissible_or_excluded``: deterministically excluded by a gate check
    """
    plausibly_viable: List[Dict[str, Any]] = []
    viable_only: List[Dict[str, Any]] = []
    inadmissible: List[Dict[str, Any]] = []

    req_rank = get_specificity_rank(required_specificity or SpecificityLevel.COMPOUND_REQUIRED.value)

    for candidate in candidates:
        if candidate.get("excluded_by_gate"):
            inadmissible.append(candidate)
            continue
        
        # Blueprint v1.2 Rank-based Selection:
        # 1. Must be governed (authoritative source + confirmed identity)
        # 2. Must meet or exceed the required specificity for this contract context
        is_governed = bool(candidate.get("governed"))
        cand_rank = get_specificity_rank(candidate.get("specificity"))
        
        if is_governed and cand_rank >= req_rank:
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
