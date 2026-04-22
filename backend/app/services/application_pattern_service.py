from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class PatternProvenance(str, Enum):
    SEED = "seed"
    PATTERN_DERIVED = "pattern_derived"


@dataclass(frozen=True, slots=True)
class FieldAutoValue:
    value: Any
    confidence: float
    provenance: PatternProvenance = PatternProvenance.PATTERN_DERIVED


@dataclass(frozen=True, slots=True)
class QuantityProfile:
    typical_min_pieces: int | None = None
    typical_max_pieces: int | None = None
    accepts_single_piece_context: bool = False


@dataclass(frozen=True, slots=True)
class ApplicationPattern:
    pattern_id: str
    canonical_name: str
    display_name: Mapping[str, str]
    triggering_contexts: tuple[str, ...]
    engineering_path: str
    typical_sealing_material_families: tuple[str, ...]
    auto_populated_fields: Mapping[str, FieldAutoValue] = field(default_factory=dict)
    required_clarification_fields: tuple[str, ...] = ()
    relevant_norm_modules: tuple[str, ...] = ()
    candidate_compound_families: tuple[str, ...] = ()
    typical_failure_modes: tuple[str, ...] = ()
    quantity_profile: QuantityProfile = field(default_factory=QuantityProfile)
    educational_note: Mapping[str, str] = field(default_factory=dict)
    version: str = "1.0"


@dataclass(frozen=True, slots=True)
class PatternCandidate:
    pattern: ApplicationPattern
    confidence: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PatternSelection:
    selected_pattern: ApplicationPattern
    proposed_fields: Mapping[str, FieldAutoValue]
    user_confirmation_required: bool = True


class ApplicationPatternLibrary:
    def __init__(self, patterns: Sequence[ApplicationPattern] | None = None) -> None:
        self._patterns = tuple(patterns or MVP_SEED_PATTERNS)
        self._by_name = {pattern.canonical_name: pattern for pattern in self._patterns}

    def list_patterns(self) -> tuple[ApplicationPattern, ...]:
        return self._patterns

    def get(self, canonical_name: str) -> ApplicationPattern | None:
        return self._by_name.get(canonical_name)

    def match(self, user_input: str, *, limit: int = 3) -> list[PatternCandidate]:
        text = _normalize(user_input)
        candidates: list[PatternCandidate] = []
        for pattern in self._patterns:
            matched = tuple(term for term in pattern.triggering_contexts if _normalize(term) in text)
            if not matched:
                continue
            candidates.append(PatternCandidate(pattern, min(0.95, 0.45 + 0.15 * len(matched)), matched))
        candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
        return candidates[:limit]

    def select(self, canonical_name: str) -> PatternSelection:
        pattern = self._by_name[canonical_name]
        return PatternSelection(pattern, dict(pattern.auto_populated_fields), True)


def _field(value: Any, confidence: float = 0.65) -> FieldAutoValue:
    return FieldAutoValue(value=value, confidence=confidence)


def _normalize(value: str) -> str:
    return " ".join((value or "").casefold().replace("-", " ").split())


MVP_SEED_PATTERNS: tuple[ApplicationPattern, ...] = (
    ApplicationPattern("pat-chemical-process-pump-aggressive-medium", "chemical_process_pump_aggressive_medium", {"de": "Chemie-Prozesspumpe"}, ("chemie", "prozesspumpe", "saeure", "base", "loesungsmittel"), "rwdr", ("ptfe_virgin", "ptfe_carbon_filled", "ptfe_graphite_filled"), {"dry_run_risk": _field(True, 0.55)}, ("medium", "temperature.max_c", "shaft.diameter_mm", "shaft_speed.rpm_nom"), ("atex", "reach"), ("ptfe_carbon_filled", "ptfe_graphite_filled", "ptfe_virgin"), ("chemical_attack", "dry_run_wear")),
    ApplicationPattern("pat-hydraulic-gearbox-standard", "hydraulic_gearbox_standard", {"de": "Hydraulik-Getriebe"}, ("hydraulik", "getriebe", "hlp46", "hlp68"), "rwdr", ("ptfe_glass_filled", "ptfe_bronze_filled"), required_clarification_fields=("pressure.max_bar", "temperature.max_c", "shaft_speed.rpm_nom")),
    ApplicationPattern("pat-food-processing-chocolate-melter", "food_processing_chocolate_melter", {"de": "Schokoladenverarbeitung"}, ("schokolade", "kakao", "lebensmittel", "cip", "sip"), "rwdr", ("ptfe_virgin", "ptfe_glass_filled"), required_clarification_fields=("food_contact_required", "cleaning.medium", "temperature.max_c"), relevant_norm_modules=("eu_food_contact", "fda_food_contact"), typical_failure_modes=("dust_induced_wear", "creep_induced_contact_loss")),
    ApplicationPattern("pat-food-processing-dairy", "food_processing_dairy", {"de": "Milchverarbeitung"}, ("milch", "molkerei", "pasteur", "joghurt", "kaese"), "rwdr", ("ptfe_virgin", "elastomer_epdm", "elastomer_fkm"), required_clarification_fields=("food_contact_required", "cleaning.medium"), relevant_norm_modules=("eu_food_contact", "fda_food_contact")),
    ApplicationPattern("pat-pharmaceutical-mixing", "pharmaceutical_mixing", {"de": "Pharma-Mischanwendung"}, ("pharma", "usp", "gmp", "steril"), "rwdr", ("ptfe_virgin", "elastomer_ffkm"), required_clarification_fields=("pharma_grade_required", "sterilization.method"), relevant_norm_modules=("usp_class_vi",)),
    ApplicationPattern("pat-water-treatment-pump", "water_treatment_pump", {"de": "Wasseraufbereitung"}, ("wasser", "trinkwasser", "abwasser", "prozesswasser"), "rwdr", ("ptfe_glass_filled", "ptfe_virgin"), required_clarification_fields=("water_approval_required", "pressure.max_bar"), relevant_norm_modules=("ktw", "nsf")),
    ApplicationPattern("pat-automotive-gearbox-axle", "automotive_gearbox_axle", {"de": "Automotive Getriebe/Achse"}, ("automotive", "achse", "fahrzeug", "iatf"), "rwdr", ("ptfe_glass_filled", "elastomer_fkm", "elastomer_hnbr"), required_clarification_fields=("quantity_requested", "temperature.max_c")),
    ApplicationPattern("pat-rotating-drum-mixer", "rotating_drum_mixer", {"de": "Rotierender Mischer"}, ("trommel", "mischer", "trockner", "partikel", "staub"), "rwdr", ("ptfe_glass_filled", "ptfe_bronze_filled"), required_clarification_fields=("abrasive_particles", "shaft_speed.rpm_nom"), typical_failure_modes=("dust_induced_wear", "lip_wear_localized")),
    ApplicationPattern("pat-compressor-sealing", "compressor_sealing", {"de": "Kompressor-Wellendichtung"}, ("kompressor", "kaeltemittel", "gas", "druckluft"), "rwdr", ("ptfe_carbon_filled", "ptfe_peek_filled"), required_clarification_fields=("pressure.max_bar", "gas_tightness_required")),
    ApplicationPattern("pat-cryogenic-or-low-temperature", "cryogenic_or_low_temperature", {"de": "Tieftemperatur"}, ("kryogen", "tieftemperatur", "-40", "-50"), "rwdr", ("ptfe_virgin", "elastomer_silicone"), required_clarification_fields=("temperature.min_c", "medium")),
    ApplicationPattern("pat-high-speed-spindle", "high_speed_spindle", {"de": "Hochdrehzahl-Spindel"}, ("spindel", "hochdrehzahl", "zentrifuge", "15 m/s"), "rwdr", ("ptfe_carbon_filled", "ptfe_peek_filled", "ptfe_graphite_filled"), required_clarification_fields=("shaft_speed.rpm_nom", "shaft.surface_ra_um")),
    ApplicationPattern("pat-pump-dry-run-risk", "pump_dry_run_risk", {"de": "Pumpe mit Trockenlauf"}, ("trockenlauf", "dosierpumpe", "niveauschutz", "leer lauf"), "rwdr", ("ptfe_graphite_filled", "ptfe_mos2_filled"), {"dry_run_risk": _field(True, 0.8)}, ("dry_run_duration", "medium"), typical_failure_modes=("dry_run_wear",)),
    ApplicationPattern("pat-rebuild-replacement-individual", "rebuild_replacement_individual", {"de": "Einzelersatz"}, ("ersatzteil", "einzelstueck", "1 stueck", "altteil", "artikelnummer"), "rwdr", ("unknown",), {"quantity_requested": _field(1, 0.75)}, ("photo_or_article_number", "dimensions"), quantity_profile=QuantityProfile(1, 10, True)),
    ApplicationPattern("pat-generic-industrial-unclear", "generic_industrial_unclear", {"de": "Unklare Industrieanwendung"}, ("dichtung", "wellendichtung", "rwdr", "simmerring"), "rwdr", ("unknown",), required_clarification_fields=("shaft.diameter_mm", "medium", "temperature.max_c", "shaft_speed.rpm_nom")),
)
