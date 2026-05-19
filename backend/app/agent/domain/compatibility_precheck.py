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
from app.mcp.calculations.chemical_resistance import lookup as lookup_chemical_resistance


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


def _all_text(profile: dict[str, Any], aliases: tuple[str, ...]) -> str:
    return " ".join(_text(profile.get(alias)) for alias in aliases if profile.get(alias) not in (None, "", [], {}))


def _has_concentration(profile: dict[str, Any]) -> tuple[str | None, bool]:
    field, value = _value(profile, _CONCENTRATION_ALIASES)
    if _is_known_text(value):
        return field, True
    qualifiers = _text(profile.get("medium_qualifiers"))
    if "%" in qualifiers or "konz" in qualifiers.casefold() or "concentration" in qualifiers.casefold():
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
    fields = [alias for alias in _EVIDENCE_ALIASES if _is_known_text(profile.get(alias))]
    return fields, bool(fields)


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
        final_approval_claim_allowed=False,
    )


def build_material_medium_compatibility_precheck(profile: dict[str, Any]) -> CompatibilityPrecheckItem:
    """Return a conservative compatibility precheck for the current profile."""

    medium_field, medium_raw = _value(profile, _MEDIUM_ALIASES)
    material_field, material_raw = _value(profile, _MATERIAL_ALIASES)
    temperature_field, temperature_raw = _value(profile, _TEMPERATURE_ALIASES)
    concentration_field, has_concentration = _has_concentration(profile)
    ph_field, has_ph = _has_ph(profile)
    evidence_fields: list[str] = []
    for field in (medium_field, material_field, temperature_field, concentration_field, ph_field):
        if field and field not in evidence_fields:
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
            evidence_fields=[field for field in evidence_fields if field != medium_field],
            missing_fields=["medium"],
            status="missing_input",
            severity="blocking",
            compatibility_claim_type="missing_medium",
            human_readable_reason="Medium fehlt oder ist nur ein Platzhalter; Werkstoffvertraeglichkeit bleibt offen.",
            allowed_user_wording="Das Medium ist noch nicht eindeutig benannt; die Werkstoffvertraeglichkeit bleibt offen.",
        )

    if not _is_known_text(material_text):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[field for field in evidence_fields if field != material_field],
            missing_fields=["material"],
            status="missing_input",
            severity="blocking",
            compatibility_claim_type="missing_material",
            human_readable_reason="Werkstoff fehlt; Medium/Werkstoff-Vertraeglichkeit kann nicht bewertet werden.",
            allowed_user_wording="Der Werkstoff ist noch nicht angegeben; eine Vertraeglichkeitsbewertung ist daher nicht moeglich.",
        )

    if material_text.strip().casefold() in {"elastomer", "kunststoff", "dichtung", "werkstoff", "material"}:
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[field for field in evidence_fields if field != material_field],
            ambiguous_fields=["material"],
            status="ambiguous_input",
            severity="blocking",
            compatibility_claim_type="ambiguous_material",
            human_readable_reason="Werkstoffangabe ist zu generisch fuer einen Material/Medium-Precheck.",
            allowed_user_wording="Der Werkstoff ist noch zu allgemein benannt; bitte Werkstofffamilie oder Compound-Richtung angeben.",
        )

    if normalized_medium_key in _GENERIC_MEDIUM_KEYS or classification.status == "family_only":
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[field for field in evidence_fields if field != medium_field],
            ambiguous_fields=["medium"],
            status="ambiguous_input",
            severity="blocking",
            compatibility_claim_type="ambiguous_medium",
            human_readable_reason="Mediumangabe ist zu generisch fuer einen Material/Medium-Precheck.",
            allowed_user_wording="Mediumgruppe bekannt, genaue Spezifikation offen.",
        )

    compliance_evidence_fields, has_compliance_evidence = _has_explicit_evidence(profile)
    if _compliance_requested(profile, medium_text) and not has_compliance_evidence:
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
        )
    evidence_fields.extend(compliance_evidence_fields)

    if temperature_raw in (None, "", [], {}):
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            evidence_fields=[field for field in evidence_fields if field != temperature_field],
            missing_fields=["temperature_c"],
            status="missing_input",
            severity="blocking",
            compatibility_claim_type="missing_temperature",
            human_readable_reason="Betriebstemperatur fehlt; der Material/Medium-Precheck ist temperaturabhaengig.",
            allowed_user_wording="Die Betriebstemperatur fehlt; sie beeinflusst die Werkstoffvertraeglichkeit deutlich.",
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
        )

    try:
        result = lookup_chemical_resistance(medium=medium_text, material=material_text)
    except KeyError:
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
            human_readable_reason="Fuer diese Medium/Werkstoff-Kombination liegt keine ausreichende deterministische Evidenz vor.",
            allowed_user_wording="Die Datenlage reicht fuer diese Medium/Werkstoff-Kombination noch nicht aus; Nachweis oder Herstellerdatenblatt erforderlich.",
        )

    if result.rating in {"C", "X"}:
        return _base_item(
            medium_field=medium_field,
            material_field=material_field,
            temperature_field=temperature_field,
            concentration_field=concentration_field,
            ph_field=ph_field,
            evidence_fields=evidence_fields,
            status="caution_zone" if result.rating == "C" else "insufficient_evidence",
            severity="high" if result.rating == "C" else "blocking",
            compatibility_claim_type="material_medium_precheck",
            human_readable_reason="Deterministische Tabelle liefert einen Warn- oder offenen Precheck-Status.",
            allowed_user_wording="Der Precheck markiert diese Kombination als Pruefpunkt; ohne Nachweis bleibt die Kompatibilitaet offen.",
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
        human_readable_reason="Bekannte Eingaben reichen fuer einen konservativen Material/Medium-Precheck.",
        allowed_user_wording="Vorlaeufiger Precheck: Der Werkstoff bleibt als Kandidat zu pruefen; ohne finalen Freigabeanspruch.",
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
    "CompatibilityStatus",
    "build_material_medium_compatibility_precheck",
    "compatibility_check_status",
]
