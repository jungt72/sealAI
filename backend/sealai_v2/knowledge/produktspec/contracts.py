"""Produktspec — Kandidaten-Spezifikation (Konzeptpapier v2). DETERMINISTIC + rule-based (no L1), so the
output is grounded by construction. The prototype SCREENS + DEFERS: with reviewed_internal knowledge it
never emits a freigegeben recommendation, only a candidate with explicit defer. Epistemics are explicit
(size_type, reifegrad, source_type, kritikalitaet); the §3.9 neutrality + DIN-copyright + liability
constraints are encoded as TYPES + invariants, not prose."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Doctrine-grounded claim boundary that travels with every spec (screening, NOT a release).
GELTUNGSRAHMEN_SPEC = (
    "Kandidaten-Spezifikation, keine technische Freigabe. Orientierung/Anfragebasis — vor Einsatz durch "
    "Hersteller bzw. Fachverantwortliche final zu prüfen (Maße, Form, Werkstoff gegen DIN + Datenblatt)."
)

# Liability/UI keystone (Konzept v2 §10): these words must never appear in spec output — tested.
VERBOTENE_WOERTER = (
    "korrekt",
    "geeignet",
    "freigegeben",
    "din-konform bestätigt",
    "bestellspezifikation",
)


class Reifegrad(str, Enum):
    DRAFT_LLM_EXTRACTED = "draft_llm_extracted"
    REVIEWED_INTERNAL = "reviewed_internal"
    EXPERT_SIGNED = "expert_signed"
    FIELD_VALIDATED = "field_validated"
    DEPRECATED = "deprecated"


# Only these reifegrade may drive a CONCRETE, non-deferred recommendation (Konzept v2 §8).
_LIVE_KONKRET = (Reifegrad.EXPERT_SIGNED, Reifegrad.FIELD_VALIDATED)


def darf_konkret_empfehlen(r: Reifegrad) -> bool:
    return r in _LIVE_KONKRET


class SourceType(str, Enum):
    STANDARD = "standard"
    TEXTBOOK = "textbook"
    EXPERT_SIGNED = "expert_signed"
    MULTI_VENDOR_COMMON = "multi_vendor_common"
    # NB: there is intentionally NO "vendor_claim" — a vendor claim may NEVER be a neutral source (§3.9).


class Kritikalitaet(str, Enum):
    NORMAL = "normal"
    CAUTION = "caution"
    HIGH_RISK = "high-risk"
    OUT_OF_SCOPE = "out-of-scope"


class Regeltyp(str, Enum):
    GRENZE = "grenze"  # disqualify (Eignungsgrenze)
    FORM = "form"  # Bauform-Vorschlag
    WERKSTOFF = "werkstoff"
    NEGATIV = "negativ"  # explicit exclusion (negative knowledge)


class SizeType(str, Enum):
    OBSERVED = "observed"  # vom User / Altdichtung / Zeichnung
    CANDIDATE = "candidate"  # aus dem Fall abgeleitet
    VERIFIED_NORM = "verified_norm"  # gegen lizenzierte/geprüfte Quelle verifiziert
    UNKNOWN = "unknown_or_unverified"


@dataclass(frozen=True)
class Bedingung:
    """A structured predicate over a Fall field — rules stay DATA (reviewable), not code."""

    feld: str
    op: str  # gt | lt | ge | le | eq | contains | present | absent
    wert: object = None


@dataclass(frozen=True)
class Auswahlregel:
    """One curated selection rule. ``source_type`` may never be a vendor claim; ``reifegrad`` gates whether
    it can drive a concrete (non-deferred) recommendation."""

    id: str
    familie: str
    regeltyp: Regeltyp
    bedingungen: tuple[Bedingung, ...]
    konsequenz: str  # e.g. "bauform:AS" | "werkstoff:FKM" | "disqualify:standard-rwdr" | "exclude:werkstoff:EPDM"
    normbezug: str
    source_type: SourceType
    reifegrad: Reifegrad
    provenance: str
    version: int = 1


@dataclass(frozen=True)
class MaßAngabe:
    feld: str
    wert: float | None
    einheit: str
    size_type: SizeType


@dataclass(frozen=True)
class Fall:
    """The distilled situation (needs analysis). Plain optional fields; absence is meaningful (drives the
    completeness gate + defer). ``rohtext`` is scanned for criticality keywords only."""

    medium: str = ""
    temperatur_c: float | None = None
    druck_bar: float | None = None
    geschwindigkeit_ms: float | None = None
    drehzahl_rpm: float | None = None
    welle_d_mm: float | None = None
    verschmutzung: bool | None = None
    gehaeuse: str = ""
    rohtext: str = ""


@dataclass(frozen=True)
class KandidatenSpec:
    """The output. NEVER carries fabricated norm dimensions (DIN tables are copyrighted + would be pseudo-
    precision) — the seal OD/width stay an open point to verify against DIN/datasheet. ``freigegeben`` is
    structurally False in the prototype (reviewed_internal knowledge only defers)."""

    familie: str
    kritikalitaet: Kritikalitaet
    bauform_din: str | None
    werkstoff: str | None
    lippen: int | None
    masse: tuple[MaßAngabe, ...]
    begruendung: tuple[str, ...]  # rule id + provenance per asserted field
    varianten: tuple[str, ...]
    konflikte: tuple[str, ...]
    offene_punkte: tuple[str, ...]
    defer_gruende: tuple[str, ...]
    teil_screening: bool
    freigegeben: bool
    geltungsrahmen: str = GELTUNGSRAHMEN_SPEC
    quellen: tuple[str, ...] = field(
        default_factory=tuple
    )  # rule ids used (provenance / recall index)
