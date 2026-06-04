"""Validation and normalization for material/medium evidence cards.

Evidence cards may support deterministic prechecks only after schema, source,
claim-level, limitation, and wording validation.  This module does not ingest
or persist documents; it is a dry-run validation seam for existing card payloads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent.domain.medium_registry import (
    classify_medium_value,
    normalize_medium_lookup_key,
)


MaterialEvidenceValidationStatus = Literal[
    "valid",
    "invalid",
    "downgraded",
    "insufficient_evidence",
]

MaterialEvidenceClaimType = Literal[
    "compatibility_observation",
    "compatibility_precheck",
    "caution",
    "limitation",
    "incompatibility_observation",
    "compliance_certificate",
    "manufacturer_datasheet_reference",
]


@dataclass(frozen=True)
class MaterialEvidenceCardValidationResult:
    card_id: str | None
    valid: bool
    status: MaterialEvidenceValidationStatus
    normalized_card: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    blocked_claims: list[str] = field(default_factory=list)
    support_allowed: bool = False
    compliance_claim_allowed: bool = False

    def to_limitation(self) -> str:
        prefix = self.card_id or "unknown_card"
        details = self.blocked_claims or self.reasons or self.limitations or [self.status]
        return f"{prefix}:{','.join(_dedupe(details))}"


SUPPORTED_SCHEMA_VERSIONS = {"material_evidence_card.v1", "material_evidence_card_v1", "v1", "1"}
VALID_CLAIM_LEVELS = {"l1": "L1", "l2": "L2", "l3": "L3"}
VALID_CLAIM_TYPES: set[str] = {
    "compatibility_observation",
    "compatibility_precheck",
    "caution",
    "limitation",
    "incompatibility_observation",
    "compliance_certificate",
    "manufacturer_datasheet_reference",
}
SUPPORTING_CLAIM_TYPES = {"compatibility_observation", "compatibility_precheck"}
COMPLIANCE_SOURCE_KEYS = ("source_url", "doi", "manufacturer", "source_hash", "certificate_id")

_GENERIC_MATERIAL_KEYS = {"material", "werkstoff", "compound", "elastomer", "kunststoff", "plastic"}
_GENERIC_MEDIUM_KEYS = {
    "oel",
    "oil",
    "chemikalie",
    "chemical",
    "reiniger",
    "cleaner",
    "reinigungsmittel",
    "saeure",
    "acid",
    "lauge",
    "loesungsmittel",
    "solvent",
}
_CONCENTRATION_DEPENDENT_KEYS = {
    "natronlauge",
    "naoh",
    "salzsaeure",
    "hcl",
    "hydrochloric acid",
    "saeure",
    "acid",
    "lauge",
    "reiniger",
    "cleaner",
    "reinigungsmittel",
}
_AGGRESSIVE_FAMILIES = {"chemisch_aggressiv", "loesemittelhaltig"}
_COMPLIANCE_CLAIM_MARKERS = {
    "fda konform",
    "atex konform",
    "trinkwasser zugelassen",
    "food approved",
    "pharma approved",
}
_FINAL_APPROVAL_MARKERS = {
    "geeignet",
    "freigegeben",
    "zugelassen",
    "validiert",
    "garantiert",
    "bestaendig gegen",
    "approved",
    "validated",
    "suitable",
    "safe for",
    "guaranteed",
    "compatible with",
}
_POSITIVE_CARD_STATUSES = {
    "a",
    "positive",
    "supported",
    "supported_precheck",
    "orientation_supported",
    "candidate",
}
_CAUTION_CARD_STATUSES = {
    "c",
    "caution",
    "caution_zone",
    "conditional",
    "limited",
    "warning",
    "review_required",
}
_NEGATIVE_CARD_STATUSES = {
    "x",
    "negative",
    "conflict",
    "conflicting",
    "not_supported",
    "incompatible",
    "contraindicated",
    "blocked",
    "avoid",
}
_MATERIAL_ALIASES = {
    "fkm": ("FKM", "FKM", None),
    "fpm": ("FKM", "FKM", "material_alias_fpm_to_fkm"),
    "viton": ("FKM", "FKM", "trade_name_alias_no_manufacturer_approval"),
    "nbr": ("NBR", "NBR", None),
    "hnbr": ("HNBR", "HNBR", None),
    "epdm": ("EPDM", "EPDM", None),
    "ptfe": ("PTFE", "PTFE", None),
    "fvmq": ("FVMQ", "FVMQ", None),
    "vmq": ("VMQ", "VMQ", None),
    "silicone": ("VMQ", "VMQ", "material_alias_silicone_to_vmq"),
    "silikon": ("VMQ", "VMQ", "material_alias_silikon_to_vmq"),
    "peek": ("PEEK", "PEEK", None),
    "uhmw pe": ("UHMW-PE", "UHMW-PE", None),
    "pe uhmw": ("UHMW-PE", "UHMW-PE", None),
    "uhmwpe": ("UHMW-PE", "UHMW-PE", None),
}


def validate_material_evidence_card(
    raw: dict[str, Any],
    *,
    seen_card_ids: set[str] | None = None,
) -> MaterialEvidenceCardValidationResult:
    """Validate one raw material evidence card without side effects."""

    if not isinstance(raw, dict):
        return MaterialEvidenceCardValidationResult(
            card_id=None,
            valid=False,
            status="invalid",
            reasons=["card_payload_not_dict"],
        )

    card_id = _text(raw.get("card_id") or raw.get("id") or raw.get("ref_id"))
    reasons: list[str] = []
    limitations: list[str] = []
    blocked_claims: list[str] = []

    if not card_id:
        reasons.append("missing_card_id")
    elif seen_card_ids is not None:
        if card_id in seen_card_ids:
            reasons.append("duplicate_card_id")
        seen_card_ids.add(card_id)

    schema_version = _text(raw.get("schema_version")).casefold()
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        reasons.append("unsupported_schema_version")

    claim_level = _normalize_claim_level(raw.get("claim_level"))
    if not claim_level:
        reasons.append("invalid_claim_level")

    claim_type = _text(raw.get("claim_type")).casefold()
    if claim_type not in VALID_CLAIM_TYPES:
        reasons.append("invalid_claim_type")

    source_title = _text(raw.get("source_title"))
    source_type = _text(raw.get("source_type"))
    has_source_anchor = any(_has_text(raw.get(key)) for key in COMPLIANCE_SOURCE_KEYS)
    if not source_type:
        reasons.append("missing_source_type")
    if not source_title or not has_source_anchor:
        reasons.append("missing_source_metadata")
    if "limitations" not in raw:
        reasons.append("missing_limitations")

    material_value = raw.get("material")
    material_family_value = raw.get("material_family")
    medium_value = raw.get("medium")
    medium_family_value = raw.get("medium_family")
    material_norm = _normalize_material(material_value)
    material_family_norm = _normalize_material(material_family_value)
    medium_norm = _normalize_medium(medium_value)
    medium_family_norm = _normalize_medium_family(medium_family_value)

    if not material_norm and not material_family_norm:
        reasons.append("missing_material_or_family")
    if not medium_norm and not medium_family_norm:
        reasons.append("missing_medium_or_family")

    if material_norm and material_norm[3]:
        limitations.append(material_norm[3])
    if material_family_norm and material_family_norm[3]:
        limitations.append(material_family_norm[3])

    material_context_only = False
    if _normalized_key(material_value) in _GENERIC_MATERIAL_KEYS:
        material_context_only = True
        limitations.append("generic_material_context_only")

    medium_context_only = False
    if medium_norm and medium_norm[2] in _GENERIC_MEDIUM_KEYS:
        medium_context_only = True
        limitations.append("generic_medium_context_only")
        medium_family_norm = medium_family_norm or (medium_norm[1], medium_norm[1])
        medium_norm = None
    if medium_family_norm and medium_family_norm[0] in _GENERIC_MEDIUM_KEYS:
        medium_context_only = True
        limitations.append("generic_medium_context_only")

    temp_min = _number(raw.get("temperature_min_c"))
    temp_max = _number(raw.get("temperature_max_c"))
    if raw.get("temperature_min_c") not in (None, "") and temp_min is None:
        reasons.append("invalid_temperature_min_c")
    if raw.get("temperature_max_c") not in (None, "") and temp_max is None:
        reasons.append("invalid_temperature_max_c")
    if temp_min is not None and temp_max is not None and temp_min > temp_max:
        reasons.append("invalid_temperature_range")

    ph_min = _number(raw.get("ph_min"))
    ph_max = _number(raw.get("ph_max"))
    if raw.get("ph_min") not in (None, "") and ph_min is None:
        reasons.append("invalid_ph_min")
    if raw.get("ph_max") not in (None, "") and ph_max is None:
        reasons.append("invalid_ph_max")
    if ph_min is not None and ph_max is not None and ph_min > ph_max:
        reasons.append("invalid_ph_range")

    limitations.extend(_list_text(raw.get("limitations")))
    concentration = _text(raw.get("concentration"))
    medium_key = medium_norm[2] if medium_norm else _text(medium_family_norm[0] if medium_family_norm else "")
    medium_family = (
        medium_norm[1]
        if medium_norm
        else _text(medium_family_norm[1] if medium_family_norm else "")
    )
    if _requires_concentration_context(medium_key, medium_family) and not concentration:
        limitations.append("missing_concentration")

    final_approval_requested = bool(raw.get("final_approval_claim_allowed"))
    compliance_requested = bool(raw.get("compliance_claim_allowed"))
    compliance_source_complete = claim_type == "compliance_certificate" and bool(
        source_title and has_source_anchor
    )
    compliance_claim_allowed = compliance_source_complete and compliance_requested

    if final_approval_requested:
        blocked_claims.append("final_approval_claim_blocked")
    if compliance_requested and not compliance_source_complete:
        blocked_claims.append("compliance_claim_without_certificate_evidence")

    statement = _text(raw.get("statement_short"))
    if not statement:
        reasons.append("missing_statement_short")
    markers = _detect_forbidden_markers(statement)
    if markers:
        compliance_only = markers.issubset(_COMPLIANCE_CLAIM_MARKERS)
        if not (compliance_only and compliance_source_complete):
            blocked_claims.extend(f"overclaim_wording:{marker}" for marker in sorted(markers))

    if reasons:
        return MaterialEvidenceCardValidationResult(
            card_id=card_id or None,
            valid=False,
            status="invalid",
            reasons=_dedupe(reasons),
            limitations=_dedupe(limitations),
            blocked_claims=_dedupe(blocked_claims),
        )

    if blocked_claims:
        return MaterialEvidenceCardValidationResult(
            card_id=card_id or None,
            valid=False,
            status="downgraded",
            reasons=["unsafe_or_final_claim_wording"],
            limitations=_dedupe([*limitations, "blocked_claim"]),
            blocked_claims=_dedupe(blocked_claims),
            support_allowed=False,
            compliance_claim_allowed=False,
        )

    normalized = {
        "schema_version": "material_evidence_card.v1",
        "card_id": card_id,
        "material": material_norm[0] if material_norm and not material_context_only else None,
        "material_family": (
            material_family_norm[0]
            if material_family_norm
            else material_norm[1]
            if material_norm
            else None
        ),
        "medium": _text(medium_value) if medium_norm and not medium_context_only else None,
        "medium_canonical": medium_norm[0] if medium_norm else None,
        "medium_family": (
            medium_family_norm[1]
            if medium_family_norm
            else medium_norm[1]
            if medium_norm
            else None
        ),
        "temperature_min_c": temp_min,
        "temperature_max_c": temp_max,
        "concentration": concentration or None,
        "ph_min": ph_min,
        "ph_max": ph_max,
        "claim_level": claim_level,
        "claim_type": claim_type,
        "statement_short": statement,
        "source_title": source_title,
        "source_type": source_type,
        "source_url": _text(raw.get("source_url")) or None,
        "doi": _text(raw.get("doi")) or None,
        "manufacturer": _text(raw.get("manufacturer")) or None,
        "evidence_date": _text(raw.get("evidence_date")) or None,
        "limitations": _dedupe(limitations),
        "final_approval_claim_allowed": False,
        "compliance_claim_allowed": compliance_claim_allowed,
        "created_by_pipeline": _text(raw.get("created_by_pipeline")) or None,
        "source_hash": _text(raw.get("source_hash")) or None,
        "certificate_id": _text(raw.get("certificate_id")) or None,
        "excerpt_short": _text(raw.get("excerpt_short") or statement) or None,
        "confidence": raw.get("confidence"),
        "supports_precheck": False,
        "requires_concentration": "missing_concentration" in limitations
        or bool(raw.get("requires_concentration")),
    }
    raw_verdict = _raw_card_verdict(raw)
    support_allowed = (
        claim_type in SUPPORTING_CLAIM_TYPES
        and claim_level in {"L2", "L3"}
        and not material_context_only
        and not medium_context_only
        and "missing_concentration" not in limitations
        and raw_verdict == "positive"
    )
    if raw_verdict == "negative" or claim_type == "incompatibility_observation":
        normalized["compatibility_status"] = "not_supported"
    elif raw_verdict == "caution" or claim_type in {
        "caution",
        "limitation",
        "manufacturer_datasheet_reference",
        "compliance_certificate",
    }:
        normalized["compatibility_status"] = "caution_zone"
    elif support_allowed:
        normalized["compatibility_status"] = "supported_precheck"
        normalized["supports_precheck"] = True
    else:
        normalized["compatibility_status"] = "caution_zone"

    status: MaterialEvidenceValidationStatus = (
        "valid" if support_allowed or normalized["compatibility_status"] != "caution_zone" else "insufficient_evidence"
    )
    return MaterialEvidenceCardValidationResult(
        card_id=card_id or None,
        valid=True,
        status=status,
        normalized_card=normalized,
        limitations=_dedupe(limitations),
        support_allowed=support_allowed,
        compliance_claim_allowed=compliance_claim_allowed,
    )


def validate_material_evidence_cards(
    cards: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[MaterialEvidenceCardValidationResult]:
    """Validate cards as one dry-run batch and reject duplicate card ids."""

    seen: set[str] = set()
    return [validate_material_evidence_card(card, seen_card_ids=seen) for card in cards]


def valid_compliance_evidence_present(cards: list[dict[str, Any]]) -> bool:
    """Return whether raw cards contain explicit compliance certificate evidence."""

    return any(
        result.valid and result.compliance_claim_allowed
        for result in validate_material_evidence_cards(cards)
    )


def _normalize_material(value: Any) -> tuple[str, str, str, str | None] | None:
    text = _text(value)
    if not text:
        return None
    key = _normalized_key(text)
    canonical, family, limitation = _MATERIAL_ALIASES.get(key, (text.upper(), text.upper(), None))
    return canonical, family, key, limitation


def _normalize_medium(value: Any) -> tuple[str, str, str] | None:
    text = _text(value)
    if not text:
        return None
    key = normalize_medium_lookup_key(text) or _normalized_key(text)
    classification = classify_medium_value(text)
    canonical = classification.canonical_label or text
    return canonical, str(classification.family or "unknown"), key


def _normalize_medium_family(value: Any) -> tuple[str, str] | None:
    text = _text(value)
    if not text:
        return None
    key = normalize_medium_lookup_key(text) or _normalized_key(text)
    family_aliases = {
        "water": "waessrig",
        "wasser": "waessrig",
        "oil": "oelhaltig",
        "oel": "oelhaltig",
        "hydraulic oil": "oelhaltig",
        "hydraulikoel": "oelhaltig",
        "acid": "chemisch_aggressiv",
        "saeure": "chemisch_aggressiv",
        "base": "chemisch_aggressiv",
        "lauge": "chemisch_aggressiv",
        "cleaner": "chemisch_aggressiv",
        "reiniger": "chemisch_aggressiv",
        "solvent": "loesemittelhaltig",
        "loesungsmittel": "loesemittelhaltig",
    }
    return key, family_aliases.get(key, key)


def _normalize_claim_level(value: Any) -> str | None:
    text = _text(value).casefold()
    return VALID_CLAIM_LEVELS.get(text)


def _requires_concentration_context(medium_key: str, medium_family: str) -> bool:
    key = medium_key.casefold()
    family = medium_family.casefold()
    return key in _CONCENTRATION_DEPENDENT_KEYS or family in _AGGRESSIVE_FAMILIES


def _detect_forbidden_markers(value: str) -> set[str]:
    normalized = _normalized_text(value)
    markers = set()
    for marker in (*_FINAL_APPROVAL_MARKERS, *_COMPLIANCE_CLAIM_MARKERS):
        if marker in normalized:
            markers.add(marker)
    return markers


def _raw_card_verdict(raw: dict[str, Any]) -> str:
    status = _text(
        raw.get("compatibility_status")
        or raw.get("status")
        or raw.get("verdict")
        or raw.get("rating")
        or raw.get("result")
    ).casefold()
    if bool(raw.get("conflicts") or raw.get("conflict")):
        return "negative"
    if status in _NEGATIVE_CARD_STATUSES:
        return "negative"
    if status in _CAUTION_CARD_STATUSES:
        return "caution"
    if status in _POSITIVE_CARD_STATUSES:
        return "positive"
    if raw.get("supports_precheck") is False:
        return "negative"
    return "positive"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has_text(value: Any) -> bool:
    return bool(_text(value))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value).replace(",", ".")
    if not text:
        return None
    try:
        return float(text.split()[0])
    except (IndexError, ValueError):
        return None


def _list_text(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    if _text(value):
        return [_text(value)]
    return []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _normalized_key(value: Any) -> str:
    text = _normalized_text(_text(value))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalized_text(value: str) -> str:
    text = value.casefold()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


__all__ = [
    "MaterialEvidenceCardValidationResult",
    "MaterialEvidenceClaimType",
    "MaterialEvidenceValidationStatus",
    "validate_material_evidence_card",
    "validate_material_evidence_cards",
    "valid_compliance_evidence_present",
]
