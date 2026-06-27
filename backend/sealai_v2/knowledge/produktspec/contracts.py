"""Produktspec v3.1 — Kandidaten-Spezifikation als Regel-Engine mit ROTEN Schranken (Konzept v3.1).
DETERMINISTIC, achsenbasiert. Grounded by construction. Hard guards (typmodell-erzwungen):
  G1 max_level = L2, review_state reviewed_internal (nie freigegeben).
  G2 free-text → candidate_set_only, NIE single_material, level ≤ L1.
  G3 final_design_code IMMER None; nur DIN_candidate_label; echtes A/AS/B nur wenn alle Achsen reviewed
     (→ erst expert_signed, im Prototyp nie).
Epistemik (envelope-band, response-level, axis-status, material-source, size_type) ist explizit."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

GELTUNGSRAHMEN_SPEC = (
    "Kandidaten-Spezifikation (Screening), keine technische Freigabe. Vor Einsatz durch Hersteller bzw. "
    "Fachverantwortliche final zu prüfen (Achsen, Werkstoff, Maße gegen DIN + Datenblatt)."
)
VERBOTENE_WOERTER = (
    "korrekt",
    "geeignet",
    "freigegeben",
    "din-konform bestätigt",
    "bestellspezifikation",
)


class ResponseLevel(str, Enum):
    L0_ESCALATION = "L0_escalation"
    L1_CANDIDATE_SPACE = "L1_candidate_space"
    L2_SCREENING_CANDIDATE = "L2_screening_candidate"
    # L3 expert_signed / L4 manufacturer_verified are NOT reachable in the prototype (G1).


class EnvelopeBand(str, Enum):
    GREEN_BASE = "green_base"
    GREEN_EXTENDED = "green_extended"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


class AxisStatus(str, Enum):
    OK = "ok"
    OPEN_VERIFICATION = "open_verification"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    GATE_BLOCKED = "gate_blocked"


class ApplicationMode(str, Enum):
    NEW = "new"
    PREVENTIVE_REPLACEMENT = "preventive_replacement"
    REPLACEMENT_UNKNOWN = "replacement_unknown"
    LEAKAGE_FAILURE = "leakage_failure"
    PREMATURE_FAILURE = "premature_failure"


class MediumSource(str, Enum):
    EXACT = "exact"  # exakte Bezeichnung / TDS / SDS / reviewte Fachkarte → L2 erlaubt
    FREE_TEXT = (
        "free_text"  # LLM-inferred aus Freitext → candidate_set_only, level ≤ L1 (G2)
    )


class Kritikalitaet(str, Enum):
    NORMAL = "normal"
    CAUTION = "caution"
    HIGH_RISK = "high-risk"
    OUT_OF_SCOPE = "out-of-scope"


class SizeType(str, Enum):
    OBSERVED = "observed"
    CANDIDATE = "candidate"
    VERIFIED_NORM = "verified_norm"
    UNKNOWN = "unknown_or_unverified"


@dataclass(frozen=True)
class Fall:
    """Situation (Bedarfsanalyse). Absence is meaningful (Defer/Kandidatenraum). ``medium_source`` decides
    whether a material may ever leave the candidate set (G2)."""

    medium: str = ""
    medium_class: str = (
        ""  # z.B. mineraloel, wasser, glykol_bremsfluessigkeit, hfc, hfd, silikonoel, …
    )
    medium_source: MediumSource = MediumSource.FREE_TEXT
    temperatur_c: float | None = None
    druck_bar: float | None = None
    druck_puls: bool = False
    geschwindigkeit_ms: float | None = None
    drehzahl_rpm: float | None = None
    welle_d_mm: float | None = None
    verschmutzung: bool | None = None
    schmierung_ok: bool | None = None
    belueftet: bool | None = None
    entluefter_ok: bool | None = None
    vakuum: bool = False
    axiale_sicherung_ok: bool | None = None
    welle_haerte_hrc: float | None = None
    welle_drall: bool | None = None
    gehaeuse_material: str = ""  # stahl, alu, leichtmetall, grauguss, geteilt, …
    gehaeuse: str = ""
    application_mode: ApplicationMode = ApplicationMode.NEW
    rohtext: str = ""


@dataclass(frozen=True)
class Axis:
    name: str  # lip | od | pressure | shaft | material
    value: str | None
    status: AxisStatus
    begruendung: tuple[str, ...] = ()


class MaterialKind(str, Enum):
    """Structural improvement (Fachreview): NEVER a bare 'empty' — the reason is typed."""

    CANDIDATE_SET = "candidate_set"
    EMPTY_EXCLUDED = "empty_because_excluded"
    EMPTY_UNKNOWN = "empty_because_unknown"
    SPECIAL_ESCALATION = (
        "special_escalation"  # PTFE/FFKM/steam-grade/fire-resistant — no DIN A/AS
    )
    # SINGLE_CANDIDATE is intentionally absent in the prototype (G2: no single material before expert_signed).


@dataclass(frozen=True)
class MaterialResult:
    """Werkstoff-Ergebnis: primary (engineering-bevorzugt) / alternatives (Upgrade-Optionen) /
    escalation (Sonderwerkstoff-Familie) / excluded — plus reason_codes + next_question. Engineering-
    Ranking (NBR vor HNBR) ist erlaubt + ≠ Hersteller-Ranking (§3.9 betrifft nur den Partner-Pool)."""

    kind: MaterialKind
    primary: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    escalation: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    next_question: tuple[str, ...] = ()
    # A candidate that is inherently additive-/concentration-dependent (e.g. HFC) → caps at L1 even on a
    # green envelope; only specific validation (SDS/Prüfstand) lifts it (→ expert_signed).
    validation_required: bool = False


@dataclass(frozen=True)
class KandidatenSpec:
    response_level: ResponseLevel
    envelope_band: EnvelopeBand | None
    kritikalitaet: Kritikalitaet
    axes: tuple[Axis, ...]
    material: MaterialResult
    din_candidate_label: str | None  # only a LABEL, never a final code
    final_design_code: str | None  # ALWAYS None (G3)
    masse: tuple = ()
    defer_gruende: tuple[str, ...] = ()
    open_verifications: tuple[str, ...] = ()
    offene_punkte: tuple[str, ...] = ()
    failure_mode_checklist: tuple[str, ...] = ()
    freigegeben: bool = False  # structural invariant (G1)
    geltungsrahmen: str = GELTUNGSRAHMEN_SPEC
    quellen: tuple[str, ...] = field(default_factory=tuple)

    # Compat + G2: material_single is ALWAYS None in the prototype; the candidate set = primary+alternatives.
    @property
    def material_candidate_set(self) -> tuple[str, ...]:
        return tuple(self.material.primary) + tuple(self.material.alternatives)

    @property
    def material_single(self) -> None:
        return None
