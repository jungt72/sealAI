from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol


class ProvenanceTier(str, Enum):
    REGISTRY = "registry"
    LLM_SYNTHESIS = "llm_synthesis"
    USER_PROVIDED = "user_provided"


@dataclass(frozen=True, slots=True)
class PropertyWithProvenance:
    value: Any
    provenance_tier: ProvenanceTier
    confidence: float
    disclaimer: str | None = None


@dataclass(frozen=True, slots=True)
class MediumEntry:
    medium_id: str
    canonical_name: str
    display_name: Mapping[str, str]
    aliases: tuple[str, ...]
    chemical_class: str
    aggressiveness: int
    viscosity_range_mpas: tuple[float, float] | None = None
    food_grade_applicable: bool = False
    pharmaceutical_grade_applicable: bool = False
    typical_challenges: tuple[str, ...] = ()
    compound_compatibility_notes: Mapping[str, str] = field(default_factory=dict)
    version: str = "1.0"


@dataclass(frozen=True, slots=True)
class CompoundRecommendation:
    compound_family: str
    rationale: str
    confidence: float


@dataclass(frozen=True, slots=True)
class MediumIntelligenceResult:
    matched_registry_entry: MediumEntry | None
    llm_synthesized_properties: Mapping[str, PropertyWithProvenance]
    medium_summary: str
    material_selection_rationale: str
    compound_recommendations: tuple[CompoundRecommendation, ...]
    risk_notes: tuple[str, ...]
    confidence_level: str
    provenance_tier: ProvenanceTier


class MediumLLM(Protocol):
    def synthesize(self, medium_query: str, temperature_c: float | None, application_context: str | None) -> Mapping[str, Any]: ...


class MediumIntelligenceService:
    def __init__(self, registry: tuple[MediumEntry, ...] | None = None, llm: MediumLLM | None = None) -> None:
        self._registry = registry or MVP_MEDIUM_REGISTRY
        self._llm = llm

    def get_medium_intelligence(self, medium_query: str, temperature_c: float | None = None, application_context: str | None = None) -> MediumIntelligenceResult:
        entry = self._match_registry(medium_query)
        if entry is not None:
            return _result_from_entry(entry)
        synthesized = dict(self._llm.synthesize(medium_query, temperature_c, application_context) if self._llm else {})
        props = {key: PropertyWithProvenance(value, ProvenanceTier.LLM_SYNTHESIS, 0.45, "Plausibility estimate; verify for the concrete case.") for key, value in synthesized.items()}
        summary = f"{medium_query} is not yet in the curated medium registry. SeaLAI can only provide plausibility context until concrete data is confirmed."
        return MediumIntelligenceResult(None, props, summary, "Material selection must remain a review item until registry or datasheet evidence is available.", (), ("medium_not_registry_grounded",), "low", ProvenanceTier.LLM_SYNTHESIS)

    def _match_registry(self, query: str) -> MediumEntry | None:
        normalized = _norm(query)
        for entry in self._registry:
            names = (entry.canonical_name, *entry.aliases, *entry.display_name.values())
            if any(_norm(name) == normalized or _norm(name) in normalized for name in names):
                return entry
        return None


def _result_from_entry(entry: MediumEntry) -> MediumIntelligenceResult:
    props = {
        "chemical_class": PropertyWithProvenance(entry.chemical_class, ProvenanceTier.REGISTRY, 0.9),
        "aggressiveness": PropertyWithProvenance(entry.aggressiveness, ProvenanceTier.REGISTRY, 0.9),
        "food_grade_applicable": PropertyWithProvenance(entry.food_grade_applicable, ProvenanceTier.REGISTRY, 0.9),
    }
    if entry.viscosity_range_mpas is not None:
        props["viscosity_range_mpas"] = PropertyWithProvenance(entry.viscosity_range_mpas, ProvenanceTier.REGISTRY, 0.85)
    recommendations = tuple(CompoundRecommendation(compound, note, 0.75) for compound, note in entry.compound_compatibility_notes.items())
    summary = f"{entry.display_name.get('de') or entry.canonical_name} is registry-grounded for sealing-material preselection context."
    rationale = "Registry facts can inform material preselection, but final manufacturer review remains required."
    return MediumIntelligenceResult(entry, props, summary, rationale, recommendations, tuple(entry.typical_challenges), "high", ProvenanceTier.REGISTRY)


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().replace("-", " ").split())


MVP_MEDIUM_REGISTRY: tuple[MediumEntry, ...] = (
    MediumEntry("med-hlp46", "hydraulic_oil_hlp46", {"de": "Hydraulikoel HLP46"}, ("hlp46", "hydraulikoel hlp46", "hydraulic oil hlp46"), "hydrocarbon_oil", 3, (35.0, 55.0), compound_compatibility_notes={"ptfe_glass_filled": "Good general direction where lubrication is present.", "ptfe_bronze_filled": "Often considered for lubricated oil service."}),
    MediumEntry("med-chocolate", "chocolate", {"de": "Schokolade"}, ("schokolade", "kakao", "chocolate"), "food_grade_viscous", 4, (3000.0, 20000.0), True, typical_challenges=("viscous", "sticky_residue", "food_contact"), compound_compatibility_notes={"ptfe_virgin": "Food-grade PTFE may be relevant when declarations are available.", "ptfe_glass_filled": "Filled PTFE needs grade-specific food-contact evidence."}),
    MediumEntry("med-sodium-hydroxide-10", "sodium_hydroxide_10pct", {"de": "Natronlauge 10%"}, ("natronlauge 10%", "naoh 10%", "sodium hydroxide 10%"), "base", 8, typical_challenges=("alkaline_cleaning", "chemical_attack"), compound_compatibility_notes={"ptfe_virgin": "PTFE is commonly chemically resistant, subject to temperature and grade evidence."}),
)
