"""Anwendungs-Archetypen — the §8 machine-type knowledge dimension (Produkt-Konzept §7 Dim. 4 / §8,
WIE §4 ▶ + §5.2). V2.1 Inc 1.

A new owner-reviewed knowledge store, built on the SAME pattern as the Fachkarten and the
Verträglichkeitsmatrix: a frozen record + ``Catalog`` + a typed loader with the "no LLM erdet LLM"
circularity guard. Where a Fachkarte knows a *material* and a matrix cell a *compatibility verdict*,
an archetype profile knows **what a machine type demands of the seal** — the constellation, the
seal-relevant peculiarities, the typical failure modes (ref into Dim. 5, later), the candidate
materials/forms, the interview questions it forces, and the blind spots the user typically misses.

The profile DRIVES (in G4) the understand stage: recognise the archetype → load this profile →
surface its ``interview_fragen`` + ``blinde_flecken`` into the L1 prompt — annotate-only, NEVER a
hard route. ``anwendbare_regime`` is STRUCTURAL at Inc 1 (the field exists, content stays empty until
the norms catalogue lands — WIE §3/§8).

Circularity guard (build-spec §8, mirrors ``fachkarten._card`` / ``matrix._cell``): a ``reviewed``
profile must be either (i) OWNER-CONFIRMED (provenance names owner / a reviewed trap / eval), or
(ii) DEEP-RESEARCH (carries ≥1 PRIMARY ``source``). ``draft`` profiles are flag-only (never
authoritative) and unconstrained — the Inc-1 starter profiles ship as ``draft`` and become
``reviewed`` ONLY after the owner reviews the content (HALT #3). Pure data + a typed loader — no LLM,
no network (``core`` stays I/O-free; the in-process catalog is canonical, a DB adapter is deferred).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from sealai_v2.core.contracts import GroundingFact

_SEED_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _SEED_DIR / "archetypes_seed.json"

_REVIEW_STATES = ("reviewed", "draft")
# provenance prefixes that establish path (i) owner-grounding (no external source needed)
_OWNER_PROV_PREFIXES = ("owner", "trap-correct:", "trap:", "eval:")


@dataclass(frozen=True)
class ArchetypeProfile:
    """One machine-type profile (Anhang B schema). ``anwendbare_regime`` is structural/empty at
    Inc 1. ``provenance`` is mandatory (owner-grounding audit); ``review_state`` gates authority."""

    key: str  # canonical archetype key, e.g. "getriebe", "ruehrwerk"
    review_state: str  # "reviewed" | "draft"
    provenance: tuple[
        str, ...
    ]  # owner-grounding origin (path i) or research origin (path ii)
    interview_fragen: tuple[
        str, ...
    ]  # what this machine forces to clarify (drives the interview)
    blinde_flecken: tuple[str, ...] = ()  # what the user typically overlooks here
    typische_konstellation: dict = field(default_factory=dict)
    dichtungsrelevante_besonderheiten: tuple[str, ...] = ()
    typische_versagensmodi: tuple[str, ...] = ()  # refs into Dim. 5 (built later)
    typische_eignungen: dict = field(
        default_factory=dict
    )  # {werkstoffe:[...], bauformen:[...]}
    anwendbare_regime: tuple[
        str, ...
    ] = ()  # STRUCTURAL at Inc 1 — content via the norms catalogue
    sources: tuple[str, ...] = ()  # primary citations (path ii), if any
    version: str = ""

    @property
    def reviewed(self) -> bool:
        return self.review_state == "reviewed"

    @property
    def owner_grounded(self) -> bool:
        return any(p.lower().startswith(_OWNER_PROV_PREFIXES) for p in self.provenance)


@dataclass(frozen=True)
class ArchetypeCatalog:
    profiles: tuple[ArchetypeProfile, ...]
    version: str = ""
    source: str = ""

    def reviewed(self) -> tuple[ArchetypeProfile, ...]:
        return tuple(p for p in self.profiles if p.review_state == "reviewed")

    def by_archetype(self, key: str) -> ArchetypeProfile | None:
        """Look up a profile by its canonical key (the G4 recognition hook). Case-insensitive."""
        k = (key or "").strip().lower()
        for p in self.profiles:
            if p.key == k:
                return p
        return None

    # alias mirroring the Fachkarten/Matrix ``by_id`` naming for catalog symmetry
    by_key = by_archetype

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(p.key for p in self.profiles)


def _profile(raw: dict) -> ArchetypeProfile:
    key = str(raw["key"]).strip().lower()
    if not key:
        raise ValueError("archetype: key is mandatory")
    state = str(raw.get("review_state", "")).strip()
    if state not in _REVIEW_STATES:
        raise ValueError(f"{key}: review_state {state!r} not in {_REVIEW_STATES}")
    if not raw.get("provenance"):
        raise ValueError(f"{key}: provenance is mandatory (owner-grounding audit)")
    provenance = tuple(str(p) for p in raw["provenance"])
    sources = tuple(str(s) for s in raw.get("sources", []))
    interview = tuple(str(q) for q in raw.get("interview_fragen", []))
    if not interview:
        raise ValueError(f"{key}: interview_fragen is mandatory (drives the interview)")
    prof = ArchetypeProfile(
        key=key,
        review_state=state,
        provenance=provenance,
        interview_fragen=interview,
        blinde_flecken=tuple(str(b) for b in raw.get("blinde_flecken", [])),
        typische_konstellation=dict(raw.get("typische_konstellation", {}) or {}),
        dichtungsrelevante_besonderheiten=tuple(
            str(x) for x in raw.get("dichtungsrelevante_besonderheiten", [])
        ),
        typische_versagensmodi=tuple(
            str(x) for x in raw.get("typische_versagensmodi", [])
        ),
        typische_eignungen=dict(raw.get("typische_eignungen", {}) or {}),
        anwendbare_regime=tuple(str(x) for x in raw.get("anwendbare_regime", [])),
        sources=sources,
        version=str(raw.get("version", "")),
    )
    # Circularity guard — a REVIEWED profile must be path (i) owner-grounded OR path (ii) primary-sourced.
    if prof.reviewed and not (prof.owner_grounded or prof.sources):
        raise ValueError(
            f"{key}: reviewed profile has neither owner/trap/eval provenance (path i) nor a primary "
            f"source (path ii) — 'no LLM erdet LLM', model-generated profiles are forbidden"
        )
    return prof


def load_archetypes(path: Path | None = None) -> ArchetypeCatalog:
    """Load + validate the archetype seed. Raises on any circularity-guard / schema violation."""
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    profiles: list[ArchetypeProfile] = []
    seen: set[str] = set()
    for raw in data.get("profiles", []):
        p = _profile(raw)
        if p.key in seen:
            raise ValueError(f"duplicate archetype key: {p.key}")
        seen.add(p.key)
        profiles.append(p)
    return ArchetypeCatalog(
        profiles=tuple(profiles),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )


def _fold_archetype_text(value: str) -> str:
    return (
        (value or "")
        .casefold()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def exact_reviewed_archetype(
    question: str, catalog: ArchetypeCatalog | None
) -> ArchetypeProfile | None:
    """Resolve one explicitly named reviewed application profile.

    A comparison can legitimately name several machines.  In that case catalog order must never
    decide which profile wins: that made a sentence about *my mixer* inherit the gearbox profile
    merely because ``getriebe`` is stored first.  Resolve a uniquely possessed/targeted application
    (``mein Rührwerk``, ``bei meinem Getriebe``); otherwise leave the multi-application turn
    unresolved so the normal comparison/diagnosis path can handle it.
    """

    if catalog is None:
        return None
    normalized = _fold_archetype_text(question)
    matches: list[ArchetypeProfile] = []
    for profile in catalog.reviewed():
        key = _fold_archetype_text(profile.key)
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", normalized):
            matches.append(profile)
    if len(matches) <= 1:
        return matches[0] if matches else None

    targeted: list[ArchetypeProfile] = []
    for profile in matches:
        key = _fold_archetype_text(profile.key)
        if re.search(
            rf"\b(?:bei|in|fuer)\s+mein(?:e[mnrs]?|em|en|er|es)?\s+{re.escape(key)}\b|"
            rf"\bmein(?:e[mnrs]?|em|en|er|es)?\s+{re.escape(key)}\b",
            normalized,
        ):
            targeted.append(profile)
    return targeted[0] if len(targeted) == 1 else None


def reviewed_archetype_grounding_facts(
    question: str, catalog: ArchetypeCatalog | None
) -> tuple[GroundingFact, ...]:
    """Build claim-level evidence from an exact owner-reviewed application profile."""

    profile = exact_reviewed_archetype(question, catalog)
    if profile is None:
        return ()
    sources = tuple(profile.sources) or tuple(
        f"sealingAI owner-reviewed archetype profile; {item}"
        for item in profile.provenance
        if item
    )
    card_id = f"ARCHETYPE-{profile.key.upper()}"
    facts: list[GroundingFact] = list(
        GroundingFact(
            text=text,
            quelle=(
                f"Archetyp {profile.key} (owner-reviewed; "
                f"{', '.join(profile.provenance)})"
            ),
            card_id=card_id,
            sources=sources,
            claim_kind="system_dependent",
            answer_facets=(
                "applications",
                "operating_factors",
                "selection_inputs",
                "failure_modes",
            ),
            subject_type="application",
            claim_id=f"{card_id}:{index}",
        )
        for index, text in enumerate(profile.dichtungsrelevante_besonderheiten)
        if text
    )
    next_index = len(facts)
    pressure_vacuum = str(
        profile.typische_konstellation.get("druck_vakuum") or ""
    ).strip()
    if pressure_vacuum:
        facts.append(
            GroundingFact(
                text=f"Druck- und Vakuumbetrieb sind anwendungsspezifisch zu prüfen: {pressure_vacuum}.",
                quelle=(
                    f"Archetyp {profile.key} (owner-reviewed; "
                    f"{', '.join(profile.provenance)})"
                ),
                card_id=card_id,
                sources=sources,
                claim_kind="system_dependent",
                answer_facets=("operating_factors", "selection_inputs"),
                subject_type="application",
                claim_id=f"{card_id}:{next_index}",
            )
        )
        next_index += 1
    for form in profile.typische_eignungen.get("bauformen", ()):
        form_text = str(form).strip()
        if not form_text:
            continue
        facts.append(
            GroundingFact(
                text=f"Bauform-Kandidat: {form_text}.",
                quelle=(
                    f"Archetyp {profile.key} (owner-reviewed; "
                    f"{', '.join(profile.provenance)})"
                ),
                card_id=card_id,
                sources=sources,
                claim_kind="system_dependent",
                answer_facets=("design_interfaces", "applications", "selection_inputs"),
                subject_type="application",
                claim_id=f"{card_id}:{next_index}",
            )
        )
        next_index += 1
    return tuple(facts)
