"""Deterministic answer profiles for engineering knowledge turns.

The LLM is the renderer, not the owner of answer depth.  This module maps a
knowledge/comparison question to an explicit engineering answer profile and
measures which profile facets are backed by reviewed grounding facts.  It is
pure: no I/O, no model call and no dependency on the knowledge store.

The profile deliberately describes *what an engineer needs to see*, not what
the model happens to remember.  Missing evidence therefore stays visible and
can be filled by curation/retrieval instead of being papered over by fluent
prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sealai_v2.core.medium_extract import extract_media
from sealai_v2.core.text_match import query_tokens, tag_matches

if TYPE_CHECKING:
    from sealai_v2.core.contracts import GroundingFact


ANSWER_FACETS = frozenset(
    {
        "definition",
        "mechanism",
        "properties",
        "parameters",
        "variants",
        "tradeoffs",
        "media_compatibility",
        "applications",
        "operating_factors",
        "design_interfaces",
        "limits",
        "failure_modes",
        "selection_inputs",
        "standards_validation",
    }
)

SUBJECT_TYPES = frozenset({"material", "medium", "seal_type", "method", "general"})

_COMPARISON_RE = re.compile(
    r"\b(vergleich\w*|unterschied\w*|unterscheid\w*|gegenüber|gegenueber|besser|schlechter|"
    r"vor-\s*und\s*nachteile|vs\.?|versus)\b",
    re.IGNORECASE,
)
_KNOWLEDGE_RE = re.compile(
    r"\b(was\s+ist|was\s+sind|erkl(?:a|ä|ae)r\w*|einordnen|definition|grundlagen|details|"
    r"informationen|[uü]berblick|eigenschaften|kennwerte|grenzwerte|aufbau|"
    r"wie\s+funktioniert|funktionsweise|vergleich\w*|unterschied\w*)\b",
    re.IGNORECASE,
)
_MEDIUM_CONTEXT_RE = re.compile(
    r"\b(dichtungsmedium|betriebsmedium|hydraulikmedium\w*|medium|medien|fluid|betriebsstoff|schmierstoff|"
    r"prozessfluid|reinigungsfluid|chemikalie)\b",
    re.IGNORECASE,
)
_METHOD_KNOWLEDGE_RE = re.compile(
    r"\b(bewert\w*|pr(?:ü|ue)fmethod\w*|kompatibilit(?:ä|ae)tspr(?:ü|ue)fung\w*|"
    r"vertr(?:ä|ae)glich\w*)\b",
    re.IGNORECASE,
)
# A bare digit is a cheap, reliable proxy for "this message states an actual case parameter"
# (dimension, speed, temperature, pressure, ...) -- used below to keep a reviewed material/
# seal-type alias mention from being treated as content-free when it is really one named entity
# inside a real engineering case.
_DIGIT_RE = re.compile(r"\d")

# Purely conversational/request scaffolding -- greetings, politeness, pronouns, the vague
# "etwas ueber X" reference, and the request verbs themselves ("kannst du ... sagen/erklaeren").
# Used only to recognize a message as content-free ASIDE FROM a named material/seal-type alias
# (see ``_is_content_free_alias_mention``) -- deliberately small and closed, mirroring this
# codebase's existing curated-word-list pattern (e.g. routing.py's own smalltalk-remainder set)
# rather than trying to regex-enumerate every possible phrasing.
_CONVERSATIONAL_FILLER_TOKENS = frozenset(
    {
        "hallo",
        "hi",
        "hey",
        "guten",
        "tag",
        "morgen",
        "abend",
        "servus",
        "moin",
        "bitte",
        "danke",
        "gerne",
        "kannst",
        "koenntest",
        "könntest",
        "wuerdest",
        "würdest",
        "kann",
        "koennen",
        "können",
        "sollst",
        "du",
        "dir",
        "dich",
        "ich",
        "mir",
        "mich",
        "wir",
        "uns",
        "sie",
        "ihnen",
        "etwas",
        "was",
        "wie",
        "ueber",
        "über",
        "zu",
        "zum",
        "zur",
        "mal",
        "noch",
        "nochmal",
        "sagen",
        "sag",
        "erzaehlen",
        "erzählen",
        "erzaehl",
        "erzähl",
        "erklaeren",
        "erklären",
        "erklaer",
        "erklär",
        "geben",
        "gebe",
        "gib",
        "zeigen",
        "zeig",
        "information",
        "informationen",
        "info",
        "infos",
        "mehr",
    }
)


def _is_content_free_alias_mention(
    text: str, tokens: set[str], materials: tuple[str, ...], seals: tuple[str, ...]
) -> bool:
    """Whether ``text`` names a reviewed material/seal-type alias and carries no other
    substantive content -- i.e. every remaining token is either part of the alias itself or
    pure conversational scaffolding, and no digit is present (a real case parameter). This is
    what makes "hallo, kannst du mir etwas ueber ptfe sagen?" trigger a knowledge profile
    without also triggering for a query like "lebensmittelechte Dichtung fuer eine
    Schokoladen-Anlage, EPDM food-grade?", which names EPDM but is really a specific
    compatibility question that must stay on its own, more targeted retrieval path."""

    if not (materials or seals) or _DIGIT_RE.search(text):
        return False
    alias_tokens: set[str] = set()
    for canonical in materials:
        for alias in _MATERIAL_ALIASES.get(canonical, ()):
            alias_tokens |= query_tokens(alias)
    for canonical in seals:
        for alias in _SEAL_ALIASES.get(canonical, ()):
            alias_tokens |= query_tokens(alias)
    return not (tokens - alias_tokens - _CONVERSATIONAL_FILLER_TOKENS)


_MATERIAL_ALIASES: dict[str, tuple[str, ...]] = {
    "PTFE": ("ptfe", "polytetrafluorethylen", "polytetrafluoroethylene"),
    "NBR": ("nbr", "nitrilkautschuk", "acrylnitril-butadien-kautschuk"),
    "HNBR": ("hnbr", "hydrierter nitrilkautschuk", "hydriertes nbr"),
    "FKM": ("fkm", "fpm", "fluorelastomer", "viton"),
    "FFKM": ("ffkm", "perfluorelastomer"),
    "FEPM": ("fepm", "aflas"),
    "EPDM": ("epdm", "ethylen-propylen-dien-kautschuk"),
    "VMQ": ("vmq", "silikonkautschuk", "silikon"),
    "ACM": ("acm", "polyacrylat-kautschuk", "acrylatkautschuk"),
    "CR": ("cr", "chloropren-kautschuk", "neopren"),
    "TPU": ("tpu", "polyurethan", "pu"),
    "PEEK": ("peek",),
    "POM": ("pom",),
}

_SEAL_ALIASES: dict[str, tuple[str, ...]] = {
    "O-Ring": ("o-ring", "oring"),
    "X-Ring": ("x-ring", "quad-ring"),
    "RWDR": (
        "rwdr",
        "radialwellendichtring",
        "radial-wellendichtring",
        "radialwellendichtung",
        "simmerring",
        "wellendichtring",
    ),
    "Gleitringdichtung": (
        "gleitringdichtung",
        "gleitdichtung",
        "glrd",
        "mechanical seal",
        "mechanische dichtung",
    ),
    "V-Ring": ("v-ring",),
    "Nutring": ("nutring",),
    "Hydraulikdichtung": (
        "hydraulikdichtung",
        "stangendichtung",
        "kolbendichtung",
        "abstreifer",
    ),
    "Flachdichtung": ("flachdichtung", "flanschdichtung"),
    "Stopfbuchspackung": ("stopfbuchspackung", "packungsdichtung"),
}

_PROFILE_ROUTES = frozenset(
    {
        "general_sealing_knowledge",
        "material_knowledge",
        "material_comparison",
    }
)


@dataclass(frozen=True)
class KnowledgeSection:
    heading: str
    instruction: str
    facets: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeAnswerPlan:
    profile: str
    subject_type: str
    subjects: tuple[str, ...]
    comparison: bool
    sections: tuple[KnowledgeSection, ...]
    available_facets: tuple[str, ...]
    subject_facets: tuple[tuple[str, tuple[str, ...]], ...]
    # One tuple of facts per entry in ``sections`` (same order, same length) -- each fact
    # appears under exactly one section, never more than one. See ``_assign_facts_to_sections``.
    section_facts: tuple[tuple["GroundingFact", ...], ...]
    # Facts whose facets matched no section's required facets -- kept visible instead of
    # silently dropped, but not pre-assigned to a heading.
    unassigned_facts: tuple["GroundingFact", ...]
    evidence_status: str
    evidence_fact_count: int
    evidence_document_count: int

    @property
    def required_facets(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(f for section in self.sections for f in section.facets)
        )

    def to_dict(self) -> dict:
        available = set(self.available_facets)
        required = set(self.required_facets)

        def _fact_dict(fact: "GroundingFact") -> dict:
            return {
                "text": fact.text,
                "quelle": fact.quelle,
                "card_id": getattr(fact, "card_id", ""),
                "claim_id": getattr(fact, "claim_id", ""),
            }

        return {
            "profile": self.profile,
            "subject_type": self.subject_type,
            "subjects": list(self.subjects),
            "comparison": self.comparison,
            "evidence_status": self.evidence_status,
            "evidence_fact_count": self.evidence_fact_count,
            "evidence_document_count": self.evidence_document_count,
            "available_facets": list(self.available_facets),
            "missing_facets": [
                facet for facet in self.required_facets if facet not in available
            ],
            "subject_coverage": [
                {
                    "subject": subject,
                    "covered_facets": list(facets),
                    "missing_facets": [
                        facet
                        for facet in self.required_facets
                        if facet not in set(facets)
                    ],
                    "coverage_ratio": round(
                        len(set(facets) & required) / len(required), 3
                    )
                    if required
                    else 0.0,
                }
                for subject, facets in self.subject_facets
            ],
            "sections": [
                {
                    "heading": section.heading,
                    "instruction": section.instruction,
                    "facets": list(section.facets),
                    "covered_facets": [f for f in section.facets if f in available],
                    "missing_facets": [f for f in section.facets if f not in available],
                    "facts": [_fact_dict(fact) for fact in facts],
                }
                for section, facts in zip(self.sections, self.section_facts)
            ],
            "unassigned_facts": [_fact_dict(fact) for fact in self.unassigned_facts],
        }


_MATERIAL_OVERVIEW = (
    KnowledgeSection(
        "Einordnung und Werkstoffstruktur",
        "Werkstoffklasse, Aufbau und der daraus folgende Dichtungsmechanismus.",
        ("definition", "mechanism"),
    ),
    KnowledgeSection(
        "Kennwerte und Betriebsverhalten",
        "Thermisches, mechanisches, tribologisches und chemisches Verhalten; Zahlen nur mit Bezugsbasis.",
        ("properties", "parameters", "media_compatibility"),
    ),
    KnowledgeSection(
        "Varianten und Trade-offs",
        "Compounds, Fuellstoffe oder Unterfamilien und welche Eigenschaft damit gewonnen oder verloren wird.",
        ("variants", "tradeoffs"),
    ),
    KnowledgeSection(
        "Dichtungsformen und Anwendungen",
        "Passende Bauformen, Bewegungsarten, Gegenpartner und typische Einsatzfelder.",
        ("applications", "design_interfaces"),
    ),
    KnowledgeSection(
        "Grenzen und Versagensmechanismen",
        "Nicht nur Nachteile nennen, sondern Mechanismus, ausloesende Bedingung und technische Folge.",
        ("limits", "failure_modes"),
    ),
    KnowledgeSection(
        "Auswahl und Verifikation",
        "Entscheidende Eingaben, anwendbare Norm-/Pruefbasis und was am konkreten Grade freizugeben ist.",
        ("selection_inputs", "standards_validation"),
    ),
)

_MATERIAL_COMPARISON = (
    KnowledgeSection(
        "Vergleichsbasis",
        "Werkstoffklassen und verglichene Grade sauber trennen; gleiche Bezugsbedingungen verwenden.",
        ("definition", "variants"),
    ),
    KnowledgeSection(
        "Kennwerte im gleichen Bezugsrahmen",
        "Parameter tabellarisch nur dann gegenueberstellen, wenn Pruefmethode und Bedingungen vergleichbar sind.",
        ("properties", "parameters"),
    ),
    KnowledgeSection(
        "Medien-, Temperatur- und Alterungsverhalten",
        "Rezeptur-, Konzentrations- und temperaturabhaengige Unterschiede mit Mechanismus erklaeren.",
        ("media_compatibility", "operating_factors"),
    ),
    KnowledgeSection(
        "Mechanische und tribologische Trade-offs",
        "Rueckstellung, Kriechen, Abrieb, Reibung, Extrusion und Gegenlaufflaeche auf denselben Achsen vergleichen.",
        ("tradeoffs", "design_interfaces"),
    ),
    KnowledgeSection(
        "Anwendungsfit und Grenzen",
        "Szenarien nennen, in denen jede Option gewinnt oder ausscheidet; keinen universellen Sieger kueren.",
        ("applications", "limits", "failure_modes"),
    ),
    KnowledgeSection(
        "Entscheidung und Nachweis",
        "Fehlende Falldaten, konkrete Grade, Datenblaetter und erforderliche Qualifikation benennen.",
        ("selection_inputs", "standards_validation"),
    ),
)

_SEAL_OVERVIEW = (
    KnowledgeSection(
        "Funktion und Dichtprinzip",
        "Leckagepfad, Kontakt-/Spaltmechanismus, Kraefte und Schmierfilm fachlich erklaeren.",
        ("definition", "mechanism"),
    ),
    KnowledgeSection(
        "Aufbau und Bauformen",
        "Komponenten, Varianten und die technische Auswahlwirkung jeder Variante.",
        ("variants", "tradeoffs"),
    ),
    KnowledgeSection(
        "Betriebsparameter",
        "Druck, Temperatur, Geschwindigkeit/Bewegung, Medium, Lastwechsel und deren Kopplung.",
        ("parameters", "operating_factors"),
    ),
    KnowledgeSection(
        "Schnittstellen und Werkstoffe",
        "Nut, Welle/Gegenlaufflaeche, Gehaeuse, Oberflaeche, Schmierung und Werkstoffpaarungen.",
        ("design_interfaces", "properties", "media_compatibility"),
    ),
    KnowledgeSection(
        "Einsatz und Grenzen",
        "Passende Anwendungen, konstruktive Ausschluesse und Abgrenzung zu Alternativbauformen.",
        ("applications", "limits"),
    ),
    KnowledgeSection(
        "Versagensbilder und Diagnose",
        "Schadensbild, physikalische Ursache, provozierende Bedingung und Gegenmassnahme verbinden.",
        ("failure_modes",),
    ),
    KnowledgeSection(
        "Normen, Montage und Auslegungsdaten",
        "Normbereich, Pruefung/Installation und die fuer eine konkrete Auswahl benoetigten Eingaben.",
        ("standards_validation", "selection_inputs"),
    ),
)

_SEAL_COMPARISON = (
    KnowledgeSection(
        "Dichtprinzipien im Vergleich",
        "Leckage-, Reibungs- und Vorspannmechanismus auf denselben Achsen vergleichen.",
        ("definition", "mechanism"),
    ),
    KnowledgeSection(
        "Bauformen und Schnittstellen",
        "Bauraum, Welle/Nut/Gehaeuse, Oberflaeche, Hilfssysteme und Montageaufwand vergleichen.",
        ("variants", "design_interfaces"),
    ),
    KnowledgeSection(
        "Betriebsfenster und Medien",
        "Druck, Temperatur, Geschwindigkeit, Bewegung, Schmierung und Medienwirkung konditioniert vergleichen.",
        ("parameters", "operating_factors", "media_compatibility"),
    ),
    KnowledgeSection(
        "Trade-offs, Grenzen und Ausfallrisiken",
        "Keine pauschale Rangfolge; je Szenario Vorteile, Grenzen und dominante Versagensarten zeigen.",
        ("tradeoffs", "limits", "failure_modes"),
    ),
    KnowledgeSection(
        "Auswahlmatrix und Nachweis",
        "Anwendungsfit, fehlende Eingaben, Normbasis und Qualifikationspfad transparent machen.",
        ("applications", "selection_inputs", "standards_validation"),
    ),
)

_MEDIUM_OVERVIEW = (
    KnowledgeSection(
        "Stoffidentitaet und Zusammensetzung",
        "Handelsprodukt, Grundfluid, Konzentration, Wasseranteil, Additive und Verunreinigungen trennen.",
        ("definition", "variants"),
    ),
    KnowledgeSection(
        "Dichtungsrelevante Stoffdaten",
        "Aggregatzustand, Viskositaet, Dichte, Dampfdruck/Phasenwechsel, Schmierfaehigkeit und Temperaturbezug.",
        ("properties", "parameters"),
    ),
    KnowledgeSection(
        "Werkstoffwechselwirkungen",
        "Quellung, Extraktion/Schrumpfung, Haertung/Erweichung, Hydrolyse/Oxidation, Permeation und RGD pruefen.",
        ("media_compatibility", "failure_modes"),
    ),
    KnowledgeSection(
        "Auswirkung auf Dichtungssysteme",
        "Folgen fuer Reibung, Schmierfilm, Waerme, Leckage, Bauform und Werkstoffpaarung erklaeren.",
        ("mechanism", "applications", "operating_factors"),
    ),
    KnowledgeSection(
        "Grenzen und Pruefpfad",
        "Betriebsbedingungen, fehlende Produktdaten, Immersions-/Systemtest und Herstellerfreigabe nennen.",
        ("limits", "selection_inputs", "standards_validation"),
    ),
)

_GENERAL_OVERVIEW = (
    KnowledgeSection(
        "Definition und Funktionsprinzip",
        "Begriff, Systemgrenze und physikalischen Wirkmechanismus erklaeren.",
        ("definition", "mechanism"),
    ),
    KnowledgeSection(
        "Technische Einflussgroessen",
        "Entscheidende Parameter und deren Kopplungen strukturiert darstellen.",
        ("properties", "parameters", "operating_factors"),
    ),
    KnowledgeSection(
        "Bauformen, Anwendungen und Trade-offs",
        "Varianten und deren Einsatzlogik statt einer blossen Begriffsliste liefern.",
        ("variants", "applications", "tradeoffs", "design_interfaces"),
    ),
    KnowledgeSection(
        "Grenzen, Versagen und Nachweis",
        "Ausfallmechanismen, fehlende Auslegungsdaten sowie Norm-/Pruefpfad benennen.",
        ("limits", "failure_modes", "selection_inputs", "standards_validation"),
    ),
)


def _contains_alias(alias: str, tokens: set[str], normalized: str) -> bool:
    return tag_matches(alias, tokens, normalized)


def _detected_materials(
    material_terms: tuple[str, ...], tokens: set[str], normalized: str
) -> tuple[str, ...]:
    found: list[tuple[int, str]] = []
    consumed: set[str] = set()
    for canonical, aliases in _MATERIAL_ALIASES.items():
        positions = [
            normalized.find(alias.lower())
            for alias in aliases
            if _contains_alias(alias, tokens, normalized)
        ]
        positions = [position for position in positions if position >= 0]
        if positions:
            found.append((min(positions), canonical))
            consumed.update(alias.lower() for alias in aliases)
    for term in material_terms:
        clean = str(term).strip()
        if (
            not clean
            or clean.lower() in consumed
            or not _contains_alias(clean, tokens, normalized)
        ):
            continue
        if clean not in {canonical for _position, canonical in found}:
            position = normalized.find(clean.lower())
            found.append((position if position >= 0 else len(normalized), clean))
    found.sort(key=lambda item: item[0])
    return tuple(canonical for _position, canonical in found)


def detected_material_subjects(
    text: str, *, material_terms: tuple[str, ...] = ()
) -> tuple[str, ...]:
    """Return canonical material subjects explicitly named in ``text``.

    This is the shared, deterministic entity boundary for routing, retrieval and
    answer planning.  It deliberately inspects only the supplied text; callers
    that resolve a follow-up must decide separately which prior user turn is
    trustworthy and relevant.
    """
    normalized = (text or "").lower()
    return _detected_materials(material_terms, query_tokens(text or ""), normalized)


def _detected_seals(tokens: set[str], normalized: str) -> tuple[str, ...]:
    return tuple(
        canonical
        for canonical, aliases in _SEAL_ALIASES.items()
        if any(_contains_alias(alias, tokens, normalized) for alias in aliases)
    )


def detected_seal_subjects(text: str) -> tuple[str, ...]:
    """Return canonical seal-type subjects explicitly named in ``text``.

    Follow-up resolution uses the same vocabulary as answer planning.  Keeping
    this boundary public prevents a second, drifting list of seal aliases in the
    conversation layer.
    """
    normalized = (text or "").lower()
    return _detected_seals(query_tokens(text or ""), normalized)


def _fallback_facets(claim_kind: str) -> tuple[str, ...]:
    return {
        "definition": ("definition",),
        "example_value": ("parameters",),
        "regulatory_status": ("standards_validation",),
        "qualification_required": ("selection_inputs", "standards_validation"),
        "safety_nogo": ("limits", "failure_modes"),
        "safety_caution": ("limits", "failure_modes"),
        "system_dependent": ("operating_factors", "design_interfaces", "tradeoffs"),
        "family_tendency": ("properties",),
    }.get(claim_kind, ())


def facets_for_fact(fact: "GroundingFact") -> tuple[str, ...]:
    explicit = tuple(
        facet for facet in getattr(fact, "answer_facets", ()) if facet in ANSWER_FACETS
    )
    return explicit or _fallback_facets(getattr(fact, "claim_kind", ""))


def _assign_facts_to_sections(
    sections: tuple[KnowledgeSection, ...],
    grounding_facts: tuple["GroundingFact", ...],
) -> tuple[tuple[tuple["GroundingFact", ...], ...], tuple["GroundingFact", ...]]:
    """Deterministically place each fact under exactly one section -- its first
    facet-matching section in plan order -- so the prompt never shows the same fact under
    two different headings and the LLM never has to self-partition a shared list. A fact
    whose facets match no section's required facets goes to a trailing bucket instead of
    being silently dropped (returned separately, not attached to any section)."""
    buckets: list[list["GroundingFact"]] = [[] for _ in sections]
    unassigned: list["GroundingFact"] = []
    for fact in grounding_facts:
        fact_facets = set(facets_for_fact(fact))
        index = next(
            (
                i
                for i, section in enumerate(sections)
                if fact_facets & set(section.facets)
            ),
            None,
        )
        if index is None:
            unassigned.append(fact)
        else:
            buckets[index].append(fact)
    return tuple(tuple(bucket) for bucket in buckets), tuple(unassigned)


def facets_for_payload(payload: dict) -> tuple[str, ...]:
    explicit = tuple(
        facet for facet in payload.get("answer_facets", ()) if facet in ANSWER_FACETS
    )
    return explicit or _fallback_facets(str(payload.get("claim_kind", "")))


def _subject_aliases(subject: str) -> tuple[str, ...]:
    if subject in _MATERIAL_ALIASES:
        return (subject, *_MATERIAL_ALIASES[subject])
    if subject in _SEAL_ALIASES:
        return (subject, *_SEAL_ALIASES[subject])
    return (subject,)


def _fact_matches_subject(fact: "GroundingFact", subject: str) -> bool:
    haystack = f"{getattr(fact, 'card_id', '')} {getattr(fact, 'text', '')}".lower()
    tokens = query_tokens(haystack)
    return any(
        tag_matches(alias, tokens, haystack) for alias in _subject_aliases(subject)
    )


def _profile(
    question: str,
    *,
    materials: tuple[str, ...],
    seals: tuple[str, ...],
    media: tuple[str, ...],
    medium_context: bool,
    route_name: str | None,
) -> tuple[str, str, tuple[str, ...], bool, tuple[KnowledgeSection, ...]]:
    comparison = (
        bool(_COMPARISON_RE.search(question)) or route_name == "material_comparison"
    )

    if len(materials) >= 2 or (materials and comparison):
        return "material_comparison", "material", materials, True, _MATERIAL_COMPARISON
    if len(seals) >= 2 or (seals and comparison):
        return "seal_type_comparison", "seal_type", seals, True, _SEAL_COMPARISON
    if materials:
        return "material_overview", "material", materials, False, _MATERIAL_OVERVIEW
    if seals:
        return "seal_type_overview", "seal_type", seals, False, _SEAL_OVERVIEW
    if len(media) >= 2 or (media and comparison):
        return "medium_comparison", "medium", media, True, _MEDIUM_OVERVIEW
    if media or medium_context:
        return "medium_overview", "medium", media, False, _MEDIUM_OVERVIEW
    return "general_technical_overview", "general", (), comparison, _GENERAL_OVERVIEW


def build_knowledge_answer_plan(
    question: str,
    *,
    material_terms: tuple[str, ...] = (),
    grounding_facts: tuple["GroundingFact", ...] = (),
    route_name: str | None = None,
    subject_order: tuple[str, ...] = (),
    allow_case_subject_profile: bool = False,
) -> KnowledgeAnswerPlan | None:
    """Build the plan only for a real knowledge/comparison turn.

    ``route_name`` is the already-computed deterministic production route.  The
    lexical fallback exists because retrieval runs before the final route object
    is available in non-policy/test configurations.
    """
    text = (question or "").strip()
    if not text:
        return None
    tokens = query_tokens(text)
    normalized = text.lower()
    materials = detected_material_subjects(text, material_terms=material_terms)
    if subject_order:
        detected = set(materials)
        ordered = tuple(subject for subject in subject_order if subject in detected)
        materials = tuple(dict.fromkeys((*ordered, *materials)))
    seals = _detected_seals(tokens, normalized)
    media = extract_media(text)
    medium_context = bool(_MEDIUM_CONTEXT_RE.search(text))
    short_subject_query = (
        bool(materials or seals or media or medium_context) and len(tokens) <= 4
    )
    explicit_medium_method = bool(medium_context and _METHOD_KNOWLEDGE_RE.search(text))
    # 2026-07-23: a reviewed material/seal-type alias (the same closed, curated list
    # ``detected_material_subjects``/``_detected_seals`` already use everywhere else) is an
    # unambiguous subject even wrapped in conversational scaffolding -- e.g. "hallo, kannst du
    # mir etwas über ptfe sagen?" names PTFE exactly as clearly as "was ist PTFE?" does.
    # ``short_subject_query`` alone missed this because it also requires ``len(tokens) <= 4``,
    # and ``_KNOWLEDGE_RE`` has no "kannst du...sagen"-shaped alternative -- together they left
    # this exact phrasing with zero facets available, which starved ``knowledge_retrieval_limit``
    # down to k=5 and (independently) excluded the reviewed card from the deterministic
    # exact-alias Qdrant fast path and the lexical eligibility filter, since both of those gates
    # call this same function. This must stay narrow: it is NOT enough to check "no digit" --
    # e.g. "lebensmittelechte Dichtung für eine Schokoladen-Anlage, EPDM food-grade?" also names
    # a reviewed alias (EPDM) and has no digit, but is a specific compatibility question with
    # real content beyond the material name, and retrieval.py's own single-material-subject
    # narrowing (InProcessRetriever.retrieve, "Prefer cards whose identity names the requested
    # material") would then wrongly displace the actually-relevant food-grade card in favor of a
    # generic EPDM-only shortlist. ``_is_content_free_alias_mention`` requires every remaining
    # token to be either the alias itself or known conversational filler -- see its docstring.
    bare_entity_mention = _is_content_free_alias_mention(text, tokens, materials, seals)
    explicit_profile_trigger = bool(
        route_name in _PROFILE_ROUTES
        or _KNOWLEDGE_RE.search(text)
        or _COMPARISON_RE.search(text)
        or short_subject_query
        or explicit_medium_method
        or bare_entity_mention
    )
    # Fallarbeit may name both a seal type and a material. The seal profile supplies the system-
    # level interfaces and failure modes; broad material profiles would instead displace focused
    # compatibility evidence. Therefore only seal types receive this bounded case augmentation.
    named_case_seal_profile = (
        allow_case_subject_profile and bool(seals) and not explicit_profile_trigger
    )
    if not (explicit_profile_trigger or named_case_seal_profile):
        return None

    if named_case_seal_profile:
        profile, subject_type, subjects, comparison, sections = (
            "seal_type_overview",
            "seal_type",
            seals,
            False,
            _SEAL_OVERVIEW,
        )
    else:
        profile, subject_type, subjects, comparison, sections = _profile(
            text,
            materials=materials,
            seals=seals,
            media=media,
            medium_context=medium_context,
            route_name=route_name,
        )
    available = tuple(
        dict.fromkeys(
            facet for fact in grounding_facts for facet in facets_for_fact(fact)
        )
    )
    required = tuple(dict.fromkeys(f for section in sections for f in section.facets))
    subject_facets = tuple(
        (
            subject,
            tuple(
                dict.fromkeys(
                    facet
                    for fact in grounding_facts
                    if _fact_matches_subject(fact, subject)
                    for facet in facets_for_fact(fact)
                )
            ),
        )
        for subject in subjects
    )
    if comparison and len(subject_facets) >= 2 and required:
        covered_pairs = sum(
            len(set(facets) & set(required)) for _subject, facets in subject_facets
        )
        ratio = covered_pairs / (len(required) * len(subject_facets))
    else:
        ratio = (
            (len(set(available) & set(required)) / len(required)) if required else 0.0
        )
    evidence_status = (
        "complete" if ratio >= 0.75 else "partial" if ratio >= 0.35 else "sparse"
    )
    documents = {
        getattr(fact, "card_id", "")
        for fact in grounding_facts
        if getattr(fact, "card_id", "")
    }
    section_facts, unassigned_facts = _assign_facts_to_sections(
        sections, grounding_facts
    )
    return KnowledgeAnswerPlan(
        profile=profile,
        subject_type=subject_type,
        subjects=subjects,
        comparison=comparison,
        sections=sections,
        available_facets=available,
        subject_facets=subject_facets,
        section_facts=section_facts,
        unassigned_facts=unassigned_facts,
        evidence_status=evidence_status,
        evidence_fact_count=len(grounding_facts),
        evidence_document_count=len(documents),
    )


def knowledge_retrieval_limit(
    question: str, *, material_terms: tuple[str, ...] = ()
) -> int:
    """Use a wider evidence set only for explicit engineering knowledge turns."""
    plan = build_knowledge_answer_plan(question, material_terms=material_terms)
    return 12 if plan is not None else 5
