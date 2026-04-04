from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


MediumFamily = Literal[
    "waessrig",
    "waessrig_salzhaltig",
    "oelhaltig",
    "gasfoermig",
    "dampffoermig",
    "loesemittelhaltig",
    "chemisch_aggressiv",
    "lebensmittelnah",
    "partikelhaltig",
    "unknown",
]

MediumClassificationStatus = Literal[
    "recognized",
    "family_only",
    "mentioned_unclassified",
    "unavailable",
]

MediumClassificationConfidence = Literal["high", "medium", "low"]

MediumMappingConfidence = Literal[
    "confirmed",
    "estimated",
    "inferred",
    "requires_confirmation",
]


@dataclass(frozen=True)
class MediumRegistryEntry:
    registry_key: str
    canonical_label: str
    family: MediumFamily
    aliases: tuple[str, ...]
    mapping_confidence: MediumMappingConfidence = "confirmed"
    classification_confidence: MediumClassificationConfidence = "high"
    normalization_source: str = "deterministic_alias_map"
    mapping_reason: str | None = None
    followup_question: str | None = None


@dataclass(frozen=True)
class MediumClassificationDecision:
    raw_text: str | None
    canonical_label: str | None
    family: MediumFamily
    status: MediumClassificationStatus
    confidence: MediumClassificationConfidence
    normalization_source: str | None
    mapping_confidence: MediumMappingConfidence
    mapping_reason: str | None = None
    registry_key: str | None = None
    matched_alias: str | None = None
    followup_question: str | None = None


@dataclass(frozen=True)
class MediumCaptureDecision:
    raw_mentions: tuple[str, ...]
    primary_raw_text: str | None


def _normalize_lookup_token(value: str | None) -> str:
    text = str(value or "").strip().casefold()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for src, target in replacements.items():
        text = text.replace(src, target)
    text = re.sub(r"[^a-z0-9+\-./ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_REGISTRY: tuple[MediumRegistryEntry, ...] = (
    MediumRegistryEntry(
        registry_key="salzwasser",
        canonical_label="Salzwasser",
        family="waessrig_salzhaltig",
        aliases=("salzwasser",),
    ),
    MediumRegistryEntry(
        registry_key="meerwasser",
        canonical_label="Meerwasser",
        family="waessrig_salzhaltig",
        aliases=("meerwasser", "seewasser"),
    ),
    MediumRegistryEntry(
        registry_key="wasser",
        canonical_label="Wasser",
        family="waessrig",
        aliases=("wasser", "water", "reinwasser"),
    ),
    MediumRegistryEntry(
        registry_key="glykol",
        canonical_label="Glykol",
        family="waessrig",
        aliases=("glykol", "glycol"),
        mapping_confidence="estimated",
        classification_confidence="medium",
        mapping_reason="glycol_family:Wasser-Glykol-Anteil und Konzentration klaeren",
    ),
    MediumRegistryEntry(
        registry_key="oel",
        canonical_label="Öl",
        family="oelhaltig",
        aliases=(
            "öl",
            "oel",
            "oil",
            "mineralöl",
            "mineraloel",
            "hydrauliköl",
            "hydraulikoel",
            "getriebeöl",
            "getriebeoel",
            "hlp",
        ),
        mapping_confidence="estimated",
        classification_confidence="medium",
        mapping_reason="generic_oil:Öltyp nicht spezifiziert — HLP/HEES/VG klären",
        followup_question="Welcher Öltyp liegt genau an?",
    ),
    MediumRegistryEntry(
        registry_key="bio_oel",
        canonical_label="Bio-Öl",
        family="oelhaltig",
        aliases=("bio-öl", "bio-oel", "hees"),
        mapping_confidence="estimated",
        classification_confidence="medium",
        mapping_reason="bio_oil_family:Öltyp und Basis genauer einordnen",
        followup_question="Welcher Öltyp liegt genau an?",
    ),
    MediumRegistryEntry(
        registry_key="bio_oel_trade",
        canonical_label="Bio-Öl",
        family="oelhaltig",
        aliases=("ester", "panolin"),
        mapping_confidence="requires_confirmation",
        classification_confidence="medium",
        mapping_reason="trade_name_ambiguous:panolin_ester — Typ bestaetigen",
        followup_question="Welcher Öltyp liegt genau an?",
    ),
    MediumRegistryEntry(
        registry_key="kraftstoff",
        canonical_label="Kraftstoff",
        family="oelhaltig",
        aliases=("kraftstoff", "diesel", "benzin", "ethanol"),
        mapping_confidence="estimated",
        classification_confidence="medium",
        mapping_reason="fuel_family:Kraftstofftyp genauer klaeren",
    ),
    MediumRegistryEntry(
        registry_key="luft",
        canonical_label="Luft",
        family="gasfoermig",
        aliases=("luft", "air"),
    ),
    MediumRegistryEntry(
        registry_key="druckluft",
        canonical_label="Druckluft",
        family="gasfoermig",
        aliases=("druckluft", "compressed air"),
    ),
    MediumRegistryEntry(
        registry_key="stickstoff",
        canonical_label="Stickstoff",
        family="gasfoermig",
        aliases=("stickstoff", "nitrogen"),
    ),
    MediumRegistryEntry(
        registry_key="sauerstoff",
        canonical_label="Sauerstoff",
        family="gasfoermig",
        aliases=("sauerstoff", "oxygen"),
    ),
    MediumRegistryEntry(
        registry_key="dampf",
        canonical_label="Dampf",
        family="dampffoermig",
        aliases=("dampf", "steam", "heißdampf", "heissdampf"),
        mapping_confidence="requires_confirmation",
        classification_confidence="medium",
        normalization_source="deterministic_alias_map",
        mapping_reason=(
            "medium_ambiguous:Dampf — Sattdampf vs. Heißdampf unklar; "
            "Betriebstemperatur und -druck erforderlich"
        ),
        followup_question="Handelt es sich um Sattdampf oder Heißdampf, und in welchem Druck- und Temperaturbereich arbeiten Sie?",
    ),
    MediumRegistryEntry(
        registry_key="saeure",
        canonical_label="Säure",
        family="chemisch_aggressiv",
        aliases=("säure", "saeure", "acid"),
        mapping_confidence="requires_confirmation",
        classification_confidence="medium",
        mapping_reason="medium_ambiguous:Säure — Konzentration, Typ und Temperatur erforderlich",
        followup_question="Um welche Säure handelt es sich genau, in welcher Konzentration und bei welcher Temperatur?",
    ),
    MediumRegistryEntry(
        registry_key="lauge",
        canonical_label="Lauge",
        family="chemisch_aggressiv",
        aliases=("lauge",),
        mapping_confidence="requires_confirmation",
        classification_confidence="medium",
        mapping_reason="medium_ambiguous:Lauge — Konzentration und NaOH/KOH-Typ erforderlich",
        followup_question="Welche Lauge liegt an, in welcher Konzentration und bei welcher Temperatur?",
    ),
    MediumRegistryEntry(
        registry_key="loesungsmittel",
        canonical_label="Lösungsmittel",
        family="loesemittelhaltig",
        aliases=("lösungsmittel", "loesungsmittel", "solvent"),
        mapping_confidence="requires_confirmation",
        classification_confidence="medium",
        mapping_reason="medium_ambiguous:Lösungsmittel — Typ erforderlich",
        followup_question="Welches Lösungsmittel liegt genau an?",
    ),
)

_EXACT_ALIAS_MAP: dict[str, tuple[MediumRegistryEntry, str]] = {}
for _entry in _REGISTRY:
    for _alias in _entry.aliases:
        _EXACT_ALIAS_MAP[_normalize_lookup_token(_alias)] = (_entry, _alias)
    _EXACT_ALIAS_MAP.setdefault(
        _normalize_lookup_token(_entry.canonical_label),
        (_entry, _entry.canonical_label),
    )

_ALIAS_PATTERNS: list[tuple[re.Pattern[str], str]] = []
for _alias_key, (_entry, _alias) in sorted(
    _EXACT_ALIAS_MAP.items(),
    key=lambda item: len(item[0]),
    reverse=True,
):
    pattern = re.compile(rf"(?<!\w){re.escape(_alias_key)}(?!\w)", re.IGNORECASE)
    _ALIAS_PATTERNS.append((pattern, _alias))

_FAMILY_HINTS: tuple[tuple[re.Pattern[str], MediumFamily, str], ...] = (
    (
        re.compile(r"\b(?:alkalisch\w*|reinigungsloesung|reinigungsmittel|cleaner)\b", re.IGNORECASE),
        "chemisch_aggressiv",
        "deterministic_family_hint:alkalisch_reinigend",
    ),
    (
        re.compile(r"\b(?:loesung|lösung|dispersion)\b", re.IGNORECASE),
        "waessrig",
        "deterministic_family_hint:solution_like",
    ),
    (
        re.compile(r"\b(?:saeurehaltig|säurehaltig|korrosiv)\b", re.IGNORECASE),
        "chemisch_aggressiv",
        "deterministic_family_hint:corrosive",
    ),
    (
        re.compile(r"\b(?:partikel|schlamm|slurry)\b", re.IGNORECASE),
        "partikelhaltig",
        "deterministic_family_hint:particle_loaded",
    ),
)

_CAPTURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bmedium(?:\s+(?:ist|is|=|:))?\s+([a-z0-9äöüß+\-./]+(?:\s+[a-z0-9äöüß+\-./]+){0,3})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bes geht um\s+([a-z0-9äöüß+\-./]+(?:\s+[a-z0-9äöüß+\-./]+){0,3})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:muss|soll|moechte|möchte)\s+([a-z0-9äöüß+\-./]+(?:\s+[a-z0-9äöüß+\-./]+){0,3})\s+(?:abgedichtet|abdichten|getrennt|trennen|gefoerdert|gefördert|foerdern|fördern)\b",
        re.IGNORECASE,
    ),
)


def medium_registry_entries() -> tuple[MediumRegistryEntry, ...]:
    return _REGISTRY


def normalize_medium_lookup_key(value: str | None) -> str | None:
    key = _normalize_lookup_token(value)
    return key or None


def resolve_medium_entry(value: str | None) -> tuple[MediumRegistryEntry | None, str | None]:
    key = normalize_medium_lookup_key(value)
    if not key:
        return None, None
    return _EXACT_ALIAS_MAP.get(key, (None, None))


def extract_medium_mentions(text: str | None) -> MediumCaptureDecision:
    message = str(text or "").strip()
    if not message:
        return MediumCaptureDecision(raw_mentions=(), primary_raw_text=None)

    normalized_message = _normalize_lookup_token(message)
    mentions: list[str] = []

    for pattern, alias in _ALIAS_PATTERNS:
        if pattern.search(normalized_message):
            mentions.append(alias)

    for pattern in _CAPTURE_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        candidate = str(match.group(1) or "").strip(" ,.;:")
        if candidate:
            mentions.append(candidate)

    unique: list[str] = []
    seen: set[str] = set()
    for mention in mentions:
        normalized = _normalize_lookup_token(mention)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(mention.strip())

    return MediumCaptureDecision(
        raw_mentions=tuple(unique),
        primary_raw_text=unique[0] if unique else None,
    )


def classify_medium_value(value: str | None) -> MediumClassificationDecision:
    text = str(value or "").strip()
    if not text:
        return MediumClassificationDecision(
            raw_text=None,
            canonical_label=None,
            family="unknown",
            status="unavailable",
            confidence="low",
            normalization_source=None,
            mapping_confidence="requires_confirmation",
        )

    entry, matched_alias = resolve_medium_entry(text)
    if entry is not None:
        return MediumClassificationDecision(
            raw_text=text,
            canonical_label=entry.canonical_label,
            family=entry.family,
            status="recognized",
            confidence=entry.classification_confidence,
            normalization_source=entry.normalization_source,
            mapping_confidence=entry.mapping_confidence,
            mapping_reason=entry.mapping_reason,
            registry_key=entry.registry_key,
            matched_alias=matched_alias,
            followup_question=entry.followup_question,
        )

    normalized = _normalize_lookup_token(text)
    for pattern, family, source in _FAMILY_HINTS:
        if pattern.search(normalized):
            return MediumClassificationDecision(
                raw_text=text,
                canonical_label=None,
                family=family,
                status="family_only",
                confidence="medium",
                normalization_source=source,
                mapping_confidence="requires_confirmation",
                mapping_reason=f"{source}:exact_medium_unresolved",
            )

    return MediumClassificationDecision(
        raw_text=text,
        canonical_label=None,
        family="unknown",
        status="mentioned_unclassified",
        confidence="low",
        normalization_source="deterministic_capture_only",
        mapping_confidence="requires_confirmation",
        mapping_reason="medium_capture_without_classification",
    )


def classify_medium_text(text: str | None) -> tuple[MediumCaptureDecision, MediumClassificationDecision]:
    capture = extract_medium_mentions(text)
    classification = classify_medium_value(capture.primary_raw_text)
    return capture, classification
