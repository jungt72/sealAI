"""Deterministic material/medium compatibility precheck.

This module is intentionally conservative: it only emits bounded precheck
status and never a final suitability, approval, or release claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent.domain.medium_registry import (
    classify_medium_value,
    is_medium_placeholder_value,
    normalize_medium_lookup_key,
)
from app.agent.domain.material_evidence_cards import (
    validate_material_evidence_cards,
    valid_compliance_evidence_present,
)
from app.mcp.calculations.chemical_resistance import (
    lookup as lookup_chemical_resistance,
)


CompatibilityStatus = Literal[
    "supported_precheck",
    "caution_zone",
    "missing_input",
    "ambiguous_input",
    "insufficient_evidence",
    "not_applicable",
    "blocked_claim",
]

CompatibilityClaimType = Literal[
    "material_medium_precheck",
    "missing_medium",
    "missing_material",
    "missing_temperature",
    "missing_concentration",
    "ambiguous_medium",
    "ambiguous_material",
    "compliance_evidence_required",
    "final_approval_blocked",
]

CompatibilitySeverity = Literal["screening", "medium", "high", "blocking"]

CompatibilityEvidenceStatus = Literal[
    "no_evidence",
    "evidence_found",
    "insufficient_evidence",
    "conflicting_evidence",
    "compliance_evidence_required",
]


@dataclass(frozen=True)
class CompatibilityEvidenceRef:
    ref_id: str | None = None
    card_id: str | None = None
    material: str | None = None
    medium: str | None = None
    claim_level: str | None = None
    source_type: str = "knowledge_card"
    source_title: str | None = None
    source_url: str | None = None
    excerpt_short: str | None = None
    confidence: float | str | None = None
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "card_id": self.card_id,
            "material": self.material,
            "medium": self.medium,
            "claim_level": self.claim_level,
            "source_type": self.source_type,
            "source_title": self.source_title,
            "source_url": self.source_url,
            "excerpt_short": self.excerpt_short,
            "confidence": self.confidence,
            "limitations": list(dict.fromkeys(self.limitations)),
        }


@dataclass(frozen=True)
class CompatibilityEvidenceLookup:
    evidence_status: CompatibilityEvidenceStatus
    evidence_refs: list[CompatibilityEvidenceRef] = field(default_factory=list)
    evidence_summary: str = ""
    evidence_limitations: list[str] = field(default_factory=list)
    has_exact_support: bool = False
    has_family_only_support: bool = False
    has_caution: bool = False
    has_conflict: bool = False
    has_temperature_gap: bool = False
    has_concentration_gap: bool = False
    has_weak_claim_level: bool = False


@dataclass(frozen=True)
class CompatibilityPrecheckItem:
    check_id: str
    medium_field: str | None
    material_field: str | None
    temperature_field: str | None = None
    concentration_field: str | None = None
    ph_field: str | None = None
    evidence_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    ambiguous_fields: list[str] = field(default_factory=list)
    status: CompatibilityStatus = "not_applicable"
    severity: CompatibilitySeverity = "medium"
    compatibility_claim_type: CompatibilityClaimType = "material_medium_precheck"
    human_readable_reason: str = ""
    allowed_user_wording: str = ""
    forbidden_user_wording: list[str] = field(default_factory=list)
    evidence_status: CompatibilityEvidenceStatus = "no_evidence"
    evidence_refs: list[CompatibilityEvidenceRef] = field(default_factory=list)
    evidence_summary: str = ""
    evidence_limitations: list[str] = field(default_factory=list)
    final_approval_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "medium_field": self.medium_field,
            "material_field": self.material_field,
            "temperature_field": self.temperature_field,
            "concentration_field": self.concentration_field,
            "ph_field": self.ph_field,
            "evidence_fields": list(dict.fromkeys(self.evidence_fields)),
            "missing_fields": list(dict.fromkeys(self.missing_fields)),
            "ambiguous_fields": list(dict.fromkeys(self.ambiguous_fields)),
            "compatibility_status": self.status,
            "status": self.status,
            "severity": self.severity,
            "compatibility_claim_type": self.compatibility_claim_type,
            "human_readable_reason": self.human_readable_reason,
            "allowed_user_wording": self.allowed_user_wording,
            "forbidden_user_wording": list(dict.fromkeys(self.forbidden_user_wording)),
            "evidence_status": self.evidence_status,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "evidence_summary": self.evidence_summary,
            "evidence_limitations": list(dict.fromkeys(self.evidence_limitations)),
            "final_approval_claim_allowed": False,
        }


_CHECK_ID = "material_medium_compatibility_precheck"
_TEXT_UNKNOWN_VALUES = {
    "unknown",
    "unbekannt",
    "unklar",
    "nicht bekannt",
    "n/a",
    "na",
    "none",
    "null",
    "werkstoff",
    "material",
    "compound",
}
_MEDIUM_ALIASES = (
    "medium",
    "medium_name",
    "fluid",
    "chemical",
    "hydraulic_fluid",
)
_MATERIAL_ALIASES = (
    "material",
    "material_family",
    "sealing_material_family",
    "compound_family",
    "ptfe_compound_family",
)
_TEMPERATURE_ALIASES = (
    "temperature_c",
    "temperature_max_c",
    "temperature_max",
    "operating_temperature_c",
)
_CONCENTRATION_ALIASES = (
    "concentration",
    "concentration_percent",
    "medium_concentration",
    "concentration_wt_percent",
    "chemistry_concentration",
)
_PH_ALIASES = ("ph", "pH", "ph_value", "medium_ph")
_COMPLIANCE_ALIASES = (
    "compliance",
    "industry",
    "certification_requirement",
    "food_contact",
    "atex",
    "atex_or_leakage_requirement",
)
_EVIDENCE_ALIASES = (
    "compatibility_evidence",
    "compliance_evidence",
    "certificate",
    "certification_evidence",
    "manufacturer_datasheet",
    "datasheet",
    "document_evidence",
    "evidence_source",
)
_EVIDENCE_CARD_ALIASES = (
    "compatibility_evidence_cards",
    "material_knowledge_cards",
    "knowledge_cards",
    "evidence_cards",
    "material_evidence",
)
_GENERIC_MEDIUM_KEYS = {
    "oel",
    "oil",
    "chemikalie",
    "chemical",
    "reiniger",
    "reinigungsmittel",
    "cleaner",
    "saeure",
    "acid",
    "lauge",
    "loesungsmittel",
    "solvent",
}
_SPECIFIC_CONDITION_DEPENDENT_KEYS = {
    "natronlauge",
    "naoh",
    "salzsaeure",
    "hcl",
    "hydrochloric acid",
    "schwefelsaeure",
    "h2so4",
}
_AGGRESSIVE_FAMILIES = {"chemisch_aggressiv", "loesemittelhaltig"}
_COMPLIANCE_MARKERS = (
    "fda",
    "food",
    "lebensmittel",
    "drinking",
    "trinkwasser",
    "pharma",
    "atex",
    "oxygen",
    "sauerstoff",
    "gas approval",
    "gasfreigabe",
    "medical",
    "medizin",
    "regulatory",
    "zulassung",
)
_SAFE_FORBIDDEN_WORDING = [
    "Werkstoff ist geeignet.",
    "Werkstoff ist freigegeben.",
    "Werkstoff ist validiert.",
    "Material is compatible.",
    "Material is approved.",
    "FDA-konform.",
    "ATEX-konform.",
    "Trinkwasser zugelassen.",
]
_MATERIAL_NORMALIZATION = {
    "viton": "fkm",
    "perbunan": "nbr",
    "teflon": "ptfe",
    "silicone": "vmq",
    "silikon": "vmq",
}
_POSITIVE_CARD_STATUSES = {
    "a",
    "b",
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


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item or "").strip()))


def _value(profile: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str | None, Any]:
    for alias in aliases:
        value = profile.get(alias)
        if value not in (None, "", [], {}):
            return alias, value
    return None, None


def _is_known_text(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str):
        text = value.strip().casefold()
        if not text or text in _TEXT_UNKNOWN_VALUES:
            return False
    return True


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    return str(value or "").strip()


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text.split()[0])
    except (IndexError, ValueError):
        return None


def _all_text(profile: dict[str, Any], aliases: tuple[str, ...]) -> str:
    return " ".join(
        _text(profile.get(alias))
        for alias in aliases
        if profile.get(alias) not in (None, "", [], {})
    )


def _has_concentration(profile: dict[str, Any]) -> tuple[str | None, bool]:
    field, value = _value(profile, _CONCENTRATION_ALIASES)
    if _is_known_text(value):
        return field, True
    qualifiers = _text(profile.get("medium_qualifiers"))
    if (
        "%" in qualifiers
        or "konz" in qualifiers.casefold()
        or "concentration" in qualifiers.casefold()
    ):
        return "medium_qualifiers", True
    return field, False


def _has_ph(profile: dict[str, Any]) -> tuple[str | None, bool]:
    field, value = _value(profile, _PH_ALIASES)
    if _is_known_text(value):
        return field, True
    qualifiers = _text(profile.get("medium_qualifiers")).casefold()
    if "ph" in qualifiers:
        return "medium_qualifiers", True
    return field, False


def _has_explicit_evidence(profile: dict[str, Any]) -> tuple[list[str], bool]:
    fields = [
        alias for alias in _EVIDENCE_ALIASES if _is_known_text(profile.get(alias))
    ]
    return fields, bool(fields)


def _normalize_material_key(value: Any) -> str:
    text = _text(value).casefold()
    text = (
        text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    return _MATERIAL_NORMALIZATION.get(text, text)


def _list_values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if value in (None, "", [], {}):
        return []
    return [value]


def _card_id(card: dict[str, Any]) -> str | None:
    for key in ("card_id", "ref_id", "id", "evidence_id"):
        value = _text(card.get(key))
        if value:
            return value
    return None


def _iter_evidence_cards(profile: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for alias in _EVIDENCE_CARD_ALIASES:
        raw = profile.get(alias)
        for item in _list_values(raw):
            if isinstance(item, dict):
                cards.append(item)
            elif hasattr(item, "model_dump"):
                dumped = item.model_dump()
                if isinstance(dumped, dict):
                    cards.append(dumped)
    return cards


def _card_claim_rank(card: dict[str, Any]) -> int:
    claim = _text(card.get("claim_level") or card.get("claim_level_max")).casefold()
    if not claim:
        return 2
    if claim.startswith("l6"):
        return 6
    if claim.startswith("l5"):
        return 5
    if claim.startswith("l4"):
        return 4
    if claim.startswith("l3"):
        return 3
    if claim.startswith("l2"):
        return 2
    if claim.startswith("l1"):
        return 1
    if claim.startswith("l0"):
        return 0
    return 1


def _card_verdict(card: dict[str, Any]) -> str:
    raw = (
        _text(card.get("compatibility_status"))
        or _text(card.get("status"))
        or _text(card.get("verdict"))
        or _text(card.get("rating"))
        or _text(card.get("result"))
    ).casefold()
    if bool(card.get("conflicts") or card.get("conflict")):
        return "negative"
    if raw in _NEGATIVE_CARD_STATUSES:
        return "negative"
    if raw in _CAUTION_CARD_STATUSES:
        return "caution"
    if raw in _POSITIVE_CARD_STATUSES:
        return "positive"
    if card.get("supports_precheck") is True:
        return "positive"
    if card.get("supports_precheck") is False:
        return "negative"
    return "positive"


def _card_temperature_range(card: dict[str, Any]) -> tuple[float | None, float | None]:
    minimum = _as_number(
        card.get("temperature_min_c")
        or card.get("temp_min_c")
        or card.get("min_temperature_c")
    )
    maximum = _as_number(
        card.get("temperature_max_c")
        or card.get("temp_max_c")
        or card.get("max_temperature_c")
        or card.get("temp_limit_c")
    )
    raw_range = card.get("temperature_range_c") or card.get("temp_range_c")
    if isinstance(raw_range, dict):
        minimum = minimum if minimum is not None else _as_number(raw_range.get("min"))
        maximum = maximum if maximum is not None else _as_number(raw_range.get("max"))
    elif isinstance(raw_range, (list, tuple)) and len(raw_range) >= 2:
        minimum = minimum if minimum is not None else _as_number(raw_range[0])
        maximum = maximum if maximum is not None else _as_number(raw_range[1])
    return minimum, maximum


def _temperature_limitation(
    card: dict[str, Any],
    temperature_raw: Any,
) -> str | None:
    temperature = _as_number(temperature_raw)
    if temperature is None:
        return None
    minimum, maximum = _card_temperature_range(card)
    if minimum is not None and temperature < minimum:
        return "operating_temperature_below_evidence_range"
    if maximum is not None and temperature > maximum:
        return "operating_temperature_above_evidence_range"
    return None


def _card_requires_concentration(card: dict[str, Any]) -> bool:
    if bool(card.get("requires_concentration") or card.get("concentration_required")):
        return True
    required = " ".join(
        _text(item).casefold() for item in _list_values(card.get("required_fields"))
    )
    return "concentration" in required or "konzentration" in required


def _card_values(card: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        for item in _list_values(card.get(key)):
            text = _text(item)
            if text:
                values.append(text)
    return values


def _card_match_level(
    card: dict[str, Any],
    *,
    medium_key: str,
    medium_family: str,
    material_key: str,
) -> str | None:
    material_exact_values = {
        _normalize_material_key(value)
        for value in _card_values(card, "material", "compound", "materials")
    }
    material_family_values = {
        _normalize_material_key(value)
        for value in _card_values(
            card, "material_family", "material_families", "family"
        )
    }
    medium_exact_values = {
        normalize_medium_lookup_key(value) or _text(value).casefold()
        for value in _card_values(card, "medium", "media", "medium_name")
    }
    medium_family_values = {
        normalize_medium_lookup_key(value) or _text(value).casefold()
        for value in _card_values(
            card, "medium_family", "medium_families", "fluid_family"
        )
    }

    material_exact = material_key in material_exact_values
    material_family = material_key in material_family_values
    medium_exact = medium_key in medium_exact_values
    medium_family_match = (
        medium_key in medium_family_values or medium_family in medium_family_values
    )
    if not (material_exact or material_family) or not (
        medium_exact or medium_family_match
    ):
        return None
    explicit_level = _text(card.get("match_level")).casefold()
    if explicit_level in {"exact", "family"}:
        return explicit_level
    if material_exact and medium_exact:
        return "exact"
    return "family"


def _evidence_ref_from_card(card: dict[str, Any]) -> CompatibilityEvidenceRef:
    ref_id = _card_id(card)
    limitations = [
        _text(item)
        for item in _list_values(
            card.get("limitations") or card.get("evidence_limitations")
        )
        if _text(item)
    ]
    return CompatibilityEvidenceRef(
        ref_id=ref_id,
        card_id=_text(card.get("card_id") or card.get("id")) or ref_id,
        material=_text(card.get("material") or card.get("material_family")) or None,
        medium=_text(card.get("medium") or card.get("medium_family")) or None,
        claim_level=_text(card.get("claim_level") or card.get("claim_level_max"))
        or None,
        source_type=_text(card.get("source_type")) or "knowledge_card",
        source_title=_text(card.get("source_title") or card.get("title")) or None,
        source_url=_text(card.get("source_url") or card.get("url")) or None,
        excerpt_short=_text(
            card.get("excerpt_short") or card.get("excerpt") or card.get("summary")
        )
        or None,
        confidence=card.get("confidence"),
        limitations=limitations,
    )


def lookup_material_compatibility_evidence(
    profile: dict[str, Any],
    *,
    medium_text: str,
    material_text: str,
    temperature_raw: Any,
    has_concentration: bool,
    medium_family: str,
) -> CompatibilityEvidenceLookup:
    """Deterministically match supplied knowledge cards to the precheck context.

    This is intentionally adapter-shaped: tests and future retrieval code can pass
    card dictionaries in the existing profile/context without requiring live Qdrant.
    """

    medium_key = normalize_medium_lookup_key(medium_text) or medium_text.casefold()
    material_key = _normalize_material_key(material_text)
    matched: list[tuple[dict[str, Any], str]] = []
    validation_limitations: list[str] = []
    for result in validate_material_evidence_cards(_iter_evidence_cards(profile)):
        if not result.valid or result.normalized_card is None:
            validation_limitations.append(
                f"invalid_evidence_card:{result.to_limitation()}"
            )
            continue
        card = result.normalized_card
        match_level = _card_match_level(
            card,
            medium_key=medium_key,
            medium_family=medium_family,
            material_key=material_key,
        )
        if match_level:
            matched.append((card, match_level))

    if not matched:
        return CompatibilityEvidenceLookup(
            evidence_status="no_evidence",
            evidence_summary="Keine passende Material/Medium-Evidenzkarte im aktuellen Wissensbestand gefunden.",
            evidence_limitations=_dedupe(
                ["missing_compatibility_knowledge_card", *validation_limitations]
            ),
        )

    refs: list[CompatibilityEvidenceRef] = []
    limitations: list[str] = []
    positive_exact = False
    positive_family = False
    has_caution = False
    has_negative = False
    has_positive = False
    has_temperature_gap = False
    has_concentration_gap = False
    has_weak_claim_level = False

    limitations.extend(validation_limitations)
    for card, match_level in matched:
        ref = _evidence_ref_from_card(card)
        refs.append(ref)
        limitations.extend(ref.limitations)
        verdict = _card_verdict(card)
        rank = _card_claim_rank(card)
        if rank < 2:
            has_weak_claim_level = True
            limitations.append("claim_level_too_weak_for_supported_precheck")
        temperature_gap = _temperature_limitation(card, temperature_raw)
        if temperature_gap:
            has_temperature_gap = True
            limitations.append(temperature_gap)
        if _card_requires_concentration(card) and not has_concentration:
            has_concentration_gap = True
            limitations.append("missing_concentration_for_evidence_card")
        if verdict == "negative":
            has_negative = True
        elif verdict == "caution":
            has_caution = True
        else:
            has_positive = True
            if match_level == "exact":
                positive_exact = True
            else:
                positive_family = True

    conflicting = has_positive and has_negative
    if conflicting:
        evidence_status: CompatibilityEvidenceStatus = "conflicting_evidence"
        summary = "Passende Evidenzkarten widersprechen sich; kein starker Kompatibilitaetsclaim zulaessig."
    elif has_temperature_gap or has_concentration_gap or has_weak_claim_level:
        evidence_status = "insufficient_evidence"
        summary = "Evidenzkarten sind vorhanden, decken aber den aktuellen Kontext nicht ausreichend ab."
    else:
        evidence_status = "evidence_found"
        summary = "Passende Evidenzkarte(n) stuetzen einen begrenzten Material/Medium-Precheck."

    return CompatibilityEvidenceLookup(
        evidence_status=evidence_status,
        evidence_refs=refs,
        evidence_summary=summary,
        evidence_limitations=_dedupe(limitations),
        has_exact_support=positive_exact and not has_negative,
        has_family_only_support=positive_family
        and not positive_exact
        and not has_negative,
        has_caution=has_caution,
        has_conflict=conflicting,
        has_temperature_gap=has_temperature_gap,
        has_concentration_gap=has_concentration_gap,
        has_weak_claim_level=has_weak_claim_level,
    )


def _compliance_requested(profile: dict[str, Any], medium_text: str) -> bool:
    haystack = (
        _all_text(profile, _COMPLIANCE_ALIASES)
        + " "
        + _text(profile.get("requirement"))
        + " "
        + _text(profile.get("latest_user_message"))
        + " "
        + medium_text
    ).casefold()
    return any(marker in haystack for marker in _COMPLIANCE_MARKERS)


def _base_item(
    *,
    medium_field: str | None,
    material_field: str | None,
    temperature_field: str | None,
    concentration_field: str | None = None,
    ph_field: str | None = None,
    evidence_fields: list[str] | None = None,
    missing_fields: list[str] | None = None,
    ambiguous_fields: list[str] | None = None,
    status: CompatibilityStatus,
    severity: CompatibilitySeverity,
    compatibility_claim_type: CompatibilityClaimType,
    human_readable_reason: str,
    allowed_user_wording: str,
    forbidden_user_wording: list[str] | None = None,
    evidence_status: CompatibilityEvidenceStatus = "no_evidence",
    evidence_refs: list[CompatibilityEvidenceRef] | None = None,
    evidence_summary: str = "",
    evidence_limitations: list[str] | None = None,
) -> CompatibilityPrecheckItem:
    return CompatibilityPrecheckItem(
        check_id=_CHECK_ID,
        medium_field=medium_field,
        material_field=material_field,
        temperature_field=temperature_field,
        concentration_field=concentration_field,
        ph_field=ph_field,
        evidence_fields=list(evidence_fields or []),
        missing_fields=list(missing_fields or []),
        ambiguous_fields=list(ambiguous_fields or []),
        status=status,
        severity=severity,
        compatibility_claim_type=compatibility_claim_type,
        human_readable_reason=human_readable_reason,
        allowed_user_wording=allowed_user_wording,
        forbidden_user_wording=forbidden_user_wording or _SAFE_FORBIDDEN_WORDING,
        evidence_status=evidence_status,
        evidence_refs=list(evidence_refs or []),
        evidence_summary=evidence_summary,
        evidence_limitations=list(evidence_limitations or []),
        final_approval_claim_allowed=False,
    )


def build_material_medium_compatibility_precheck(
    profile: dict[str, Any],
) -> CompatibilityPrecheckItem:
    """Return a conservative compatibility precheck for the current profile."""

    medium_field, medium_raw = _value(profile, _MEDIUM_ALIASES)
    material_field, material_raw = _value(profile, _MATERIAL_ALIASES)
    temperature_field, temperature_raw = _value(profile, _TEMPERATURE_ALIASES)
    concentration_field, has_concentration = _has_concentration(profile)
    ph_field, has_ph = _has_ph(profile)
    evidence_fields: list[str] = []
    for field in (
        medium_field,
        material_field,
        temperature_field,
        concentration_field,
        ph_field,
    ):
        if field and field not in evidence_fields:
            evidence_fields.append(field)
    for field in _EVIDENCE_CARD_ALIASES:
        if _is_known_text(profile.get(field)) and field not in evidence_fields:
            evidence_fields.append(field)

    medium_text = _text(medium_raw)
    material_text = _text(material_raw)
    classification = classify_medium_value(medium_text)
    normalized_medium_key = normalize_medium_lookup_key(medium_text) or ""

    if not medium_text or is_medium_placeholder_value(medium_text):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[
                field for field in evidence_fields if field != medium_field
            ],
            missing_fields=["medium"],
            status="missing_input",
            severity="blocking",
            compatibility_claim_type="missing_medium",
            human_readable_reason="Medium fehlt oder ist nur ein Platzhalter; Werkstoffvertraeglichkeit bleibt offen.",
            allowed_user_wording="Das Medium ist noch nicht eindeutig benannt; die Werkstoffvertraeglichkeit bleibt offen.",
            evidence_summary="Keine Evidenzbewertung ohne eindeutiges Medium.",
            evidence_limitations=["missing_medium"],
        )

    if not _is_known_text(material_text):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[
                field for field in evidence_fields if field != material_field
            ],
            missing_fields=["material"],
            status="missing_input",
            severity="blocking",
            compatibility_claim_type="missing_material",
            human_readable_reason="Werkstoff fehlt; Medium/Werkstoff-Vertraeglichkeit kann nicht bewertet werden.",
            allowed_user_wording="Der Werkstoff ist noch nicht angegeben; eine Vertraeglichkeitsbewertung ist daher nicht moeglich.",
            evidence_summary="Keine Evidenzbewertung ohne Werkstoffangabe.",
            evidence_limitations=["missing_material"],
        )

    if material_text.strip().casefold() in {
        "elastomer",
        "kunststoff",
        "dichtung",
        "werkstoff",
        "material",
    }:
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[
                field for field in evidence_fields if field != material_field
            ],
            ambiguous_fields=["material"],
            status="ambiguous_input",
            severity="blocking",
            compatibility_claim_type="ambiguous_material",
            human_readable_reason="Werkstoffangabe ist zu generisch fuer einen Material/Medium-Precheck.",
            allowed_user_wording="Der Werkstoff ist noch zu allgemein benannt; bitte Werkstofffamilie oder Compound-Richtung angeben.",
            evidence_status="insufficient_evidence",
            evidence_summary="Werkstoffangabe ist fuer eine belastbare Evidenzkarte zu allgemein.",
            evidence_limitations=["ambiguous_material"],
        )

    if (
        normalized_medium_key in _GENERIC_MEDIUM_KEYS
        or classification.status == "family_only"
    ):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[
                field for field in evidence_fields if field != medium_field
            ],
            ambiguous_fields=["medium"],
            status="ambiguous_input",
            severity="blocking",
            compatibility_claim_type="ambiguous_medium",
            human_readable_reason="Mediumangabe ist zu generisch fuer einen Material/Medium-Precheck.",
            allowed_user_wording="Mediumgruppe bekannt, genaue Spezifikation offen.",
            evidence_status="insufficient_evidence",
            evidence_summary="Mediumangabe ist fuer eine belastbare Evidenzkarte zu allgemein.",
            evidence_limitations=["ambiguous_medium"],
        )

    compliance_evidence_fields, has_compliance_evidence = _has_explicit_evidence(
        profile
    )
    has_card_compliance_evidence = valid_compliance_evidence_present(
        _iter_evidence_cards(profile)
    )
    if _compliance_requested(profile, medium_text) and not (
        has_compliance_evidence or has_card_compliance_evidence
    ):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            concentration_field=concentration_field,
            ph_field=ph_field,
            evidence_fields=evidence_fields,
            missing_fields=["compliance_evidence"],
            status="blocked_claim",
            severity="blocking",
            compatibility_claim_type="compliance_evidence_required",
            human_readable_reason="Regulatorische oder Zulassungsanforderung braucht konkrete Nachweise.",
            allowed_user_wording="Fuer diese Anforderung ist ein konkreter Nachweis des Werkstoff-/Herstellerdatenblatts erforderlich.",
            evidence_status="compliance_evidence_required",
            evidence_summary="Normale Kompatibilitaetskarten ersetzen keinen Zertifikats- oder Herstellerfreigabenachweis.",
            evidence_limitations=["compliance_certificate_required"],
        )
    evidence_fields.extend(compliance_evidence_fields)
    if has_card_compliance_evidence:
        for alias in _EVIDENCE_CARD_ALIASES:
            if _is_known_text(profile.get(alias)) and alias not in evidence_fields:
                evidence_fields.append(alias)

    if temperature_raw in (None, "", [], {}):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[
                field for field in evidence_fields if field != temperature_field
            ],
            missing_fields=["temperature_c"],
            status="missing_input",
            severity="blocking",
            compatibility_claim_type="missing_temperature",
            human_readable_reason="Betriebstemperatur fehlt; der Material/Medium-Precheck ist temperaturabhaengig.",
            allowed_user_wording="Die Betriebstemperatur fehlt; sie beeinflusst die Werkstoffvertraeglichkeit deutlich.",
            evidence_status="insufficient_evidence",
            evidence_summary="Evidenzkarten koennen ohne Betriebstemperatur nicht fuer diesen Kontext bewertet werden.",
            evidence_limitations=["missing_temperature"],
        )

    evidence_lookup = lookup_material_compatibility_evidence(
        profile,
        medium_text=medium_text,
        material_text=material_text,
        temperature_raw=temperature_raw,
        has_concentration=has_concentration,
        medium_family=str(classification.family or ""),
    )

    needs_condition_detail = (
        classification.family in _AGGRESSIVE_FAMILIES
        or normalized_medium_key in _SPECIFIC_CONDITION_DEPENDENT_KEYS
        or "reiniger" in normalized_medium_key
        or "cleaner" in normalized_medium_key
    )
    if needs_condition_detail and not (has_concentration or has_ph):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            concentration_field=concentration_field,
            ph_field=ph_field,
            evidence_fields=evidence_fields,
            missing_fields=["concentration"],
            status="missing_input",
            severity="blocking",
            compatibility_claim_type="missing_concentration",
            human_readable_reason="Chemisch/aggressives Medium braucht Konzentration oder pH-Kontext.",
            allowed_user_wording="Die Konzentration bzw. der pH-Kontext fehlt; der Werkstoff-Medium-Precheck bleibt offen.",
            evidence_status="insufficient_evidence",
            evidence_refs=evidence_lookup.evidence_refs,
            evidence_summary=(
                "Evidenzbewertung bleibt begrenzt, weil Konzentration oder pH-Kontext fuer dieses Medium fehlen."
            ),
            evidence_limitations=_dedupe(
                ["missing_concentration", *evidence_lookup.evidence_limitations]
            ),
        )

    if evidence_lookup.evidence_status == "no_evidence":
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            concentration_field=concentration_field,
            ph_field=ph_field,
            evidence_fields=evidence_fields,
            missing_fields=["compatibility_evidence"],
            status="insufficient_evidence",
            severity="blocking",
            compatibility_claim_type="material_medium_precheck",
            human_readable_reason="Fuer diese Medium/Werkstoff-Kombination liegt keine ausreichende Evidenzkarte vor.",
            allowed_user_wording="Fuer diese Kombination liegt im aktuellen Wissensbestand keine belastbare Karte vor; Herstellerdatenblatt oder weitere Evidenz erforderlich.",
            evidence_status="no_evidence",
            evidence_summary=evidence_lookup.evidence_summary,
            evidence_limitations=evidence_lookup.evidence_limitations,
        )

    if evidence_lookup.evidence_status == "conflicting_evidence":
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            concentration_field=concentration_field,
            ph_field=ph_field,
            evidence_fields=evidence_fields,
            status="caution_zone",
            severity="high",
            compatibility_claim_type="material_medium_precheck",
            human_readable_reason="Evidenzkarten widersprechen sich; daraus entsteht kein starker Kompatibilitaetsclaim.",
            allowed_user_wording="Die Evidenzlage ist widerspruechlich; die Kombination bleibt ein Pruefpunkt ohne Freigabeanspruch.",
            evidence_status="conflicting_evidence",
            evidence_refs=evidence_lookup.evidence_refs,
            evidence_summary=evidence_lookup.evidence_summary,
            evidence_limitations=evidence_lookup.evidence_limitations,
        )

    if evidence_lookup.evidence_status == "insufficient_evidence":
        claim_type: CompatibilityClaimType = (
            "missing_concentration"
            if evidence_lookup.has_concentration_gap
            else "material_medium_precheck"
        )
        missing = (
            ["concentration"]
            if evidence_lookup.has_concentration_gap
            else ["compatibility_evidence"]
        )
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            concentration_field=concentration_field,
            ph_field=ph_field,
            evidence_fields=evidence_fields,
            missing_fields=missing,
            status="missing_input"
            if evidence_lookup.has_concentration_gap
            else "insufficient_evidence",
            severity="blocking",
            compatibility_claim_type=claim_type,
            human_readable_reason="Vorhandene Evidenzkarten decken den aktuellen Material/Medium-Kontext nicht ausreichend ab.",
            allowed_user_wording="Die Evidenzkarte ist fuer diesen Kontext noch nicht ausreichend; Nachweis oder Herstellerdatenblatt erforderlich.",
            evidence_status="insufficient_evidence",
            evidence_refs=evidence_lookup.evidence_refs,
            evidence_summary=evidence_lookup.evidence_summary,
            evidence_limitations=evidence_lookup.evidence_limitations,
        )

    try:
        table_result = lookup_chemical_resistance(
            medium=medium_text, material=material_text
        )
    except KeyError:
        table_result = None

    table_caution = table_result is not None and table_result.rating in {"C", "X"}
    if (
        evidence_lookup.has_family_only_support
        or evidence_lookup.has_caution
        or table_caution
    ):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            concentration_field=concentration_field,
            ph_field=ph_field,
            evidence_fields=evidence_fields,
            status="caution_zone"
            if table_result is None or table_result.rating != "X"
            else "insufficient_evidence",
            severity="high" if table_caution else "medium",
            compatibility_claim_type="material_medium_precheck",
            human_readable_reason="Evidenz reicht nur fuer Orientierung oder markiert einen Pruefpunkt.",
            allowed_user_wording="Evidenzgestuetzter Precheck: als Kandidat beziehungsweise Pruefpunkt zu behandeln; Herstellerfreigabe bleibt erforderlich.",
            evidence_status=evidence_lookup.evidence_status,
            evidence_refs=evidence_lookup.evidence_refs,
            evidence_summary=evidence_lookup.evidence_summary,
            evidence_limitations=evidence_lookup.evidence_limitations,
        )

    return _base_item(
        medium_field=medium_field,
        material_field=material_field,
        temperature_field=temperature_field,
        concentration_field=concentration_field,
        ph_field=ph_field,
        evidence_fields=evidence_fields,
        status="supported_precheck",
        severity="screening",
        compatibility_claim_type="material_medium_precheck",
        human_readable_reason="Evidenzkarte und bekannte Eingaben reichen fuer einen konservativen Material/Medium-Precheck.",
        allowed_user_wording="Evidenzgestuetzter Precheck: Der Werkstoff bleibt als Kandidat zu pruefen; ohne finalen Freigabeanspruch.",
        evidence_status="evidence_found",
        evidence_refs=evidence_lookup.evidence_refs,
        evidence_summary=evidence_lookup.evidence_summary,
        evidence_limitations=evidence_lookup.evidence_limitations,
    )


def compatibility_check_status(precheck: CompatibilityPrecheckItem) -> str:
    if precheck.status == "supported_precheck":
        return "passed"
    if precheck.status == "not_applicable":
        return "not_applicable"
    return "blocked"


__all__ = [
    "CompatibilityClaimType",
    "CompatibilityPrecheckItem",
    "CompatibilityEvidenceRef",
    "CompatibilityEvidenceStatus",
    "CompatibilityStatus",
    "build_material_medium_compatibility_precheck",
    "compatibility_check_status",
    "lookup_material_compatibility_evidence",
]
