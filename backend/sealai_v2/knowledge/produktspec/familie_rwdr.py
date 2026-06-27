"""RWDR / DIN 3760 reference family (Konzept v2 §9). The seed rules are REVIEWED_INTERNAL + illustrative
('domänen-zu-validieren') — they only DEFER, never drive a freigegeben recommendation, until a sealing
engineer signs them (expert_signed). Thresholds (~0,5 bar / ~12 m/s) per published DIN-3760 reference
values; NO DIN tables/dimension series are stored (copyright)."""

from __future__ import annotations

from sealai_v2.knowledge.produktspec.contracts import (
    Auswahlregel,
    Bedingung,
    Regeltyp,
    Reifegrad,
    SourceType,
)
from sealai_v2.knowledge.produktspec.kernel import FamilyKernel

_RI = Reifegrad.REVIEWED_INTERNAL
_STD = SourceType.STANDARD
_PROV = "Seed RWDR/DIN3760 [reviewed_internal, domänen-zu-validieren]"


def _r(rid, typ, bed, kons, *, src=_STD, norm="DIN 3760"):
    return Auswahlregel(
        id=rid,
        familie="RWDR",
        regeltyp=typ,
        bedingungen=tuple(bed),
        konsequenz=kons,
        normbezug=norm,
        source_type=src,
        reifegrad=_RI,
        provenance=_PROV,
    )


_RULES = (
    # Eignungsgrenzen (disqualify) — Standard-RWDR Richtwerte.
    _r(
        "RWDR-G-DRUCK",
        Regeltyp.GRENZE,
        [Bedingung("druck_bar", "gt", 0.5)],
        "disqualify:standard-rwdr",
    ),
    _r(
        "RWDR-G-SPEED",
        Regeltyp.GRENZE,
        [Bedingung("geschwindigkeit_ms", "gt", 12.0)],
        "disqualify:standard-rwdr",
    ),
    # Form-Regeln.
    _r(
        "RWDR-F-AS",
        Regeltyp.FORM,
        [Bedingung("verschmutzung", "eq", True)],
        "bauform:AS",
    ),
    _r(
        "RWDR-F-A",
        Regeltyp.FORM,
        [Bedingung("verschmutzung", "eq", False)],
        "bauform:A",
    ),
    _r(
        "RWDR-F-B",
        Regeltyp.FORM,
        [Bedingung("gehaeuse", "contains", "metall")],
        "bauform:B",
    ),
    # Werkstoff-Regeln (vereinfachte §4-Matrix-Logik).
    _r(
        "RWDR-W-FKM",
        Regeltyp.WERKSTOFF,
        [Bedingung("medium", "contains", "öl"), Bedingung("temperatur_c", "gt", 100.0)],
        "werkstoff:FKM",
    ),
    _r(
        "RWDR-W-NBR",
        Regeltyp.WERKSTOFF,
        [Bedingung("medium", "contains", "öl"), Bedingung("temperatur_c", "le", 100.0)],
        "werkstoff:NBR",
    ),
    _r(
        "RWDR-W-EPDM",
        Regeltyp.WERKSTOFF,
        [Bedingung("medium", "contains", "wasser")],
        "werkstoff:EPDM",
    ),
    # Negatives Wissen: EPDM nicht bei Mineralöl.
    _r(
        "RWDR-N-EPDM-OEL",
        Regeltyp.NEGATIV,
        [Bedingung("medium", "contains", "mineralöl")],
        "exclude:werkstoff:EPDM",
    ),
)

RWDR_KERNEL = FamilyKernel(
    familie="RWDR",
    norm="DIN 3760",
    required_inputs=("medium", "temperatur_c", "druck_bar", "welle_d_mm"),
    rules=_RULES,
    bauform_meta={
        "A": ("DIN 3760 – Form A (Elastomer-Außenmantel, 1 Dichtlippe)", 1),
        "AS": ("DIN 3760 – Form AS (mit Zusatz-Staublippe)", 2),
        "B": ("DIN 3760 – Form B (Metall-Außenmantel)", 1),
        "BS": ("DIN 3760 – Form BS (Metallmantel + Staublippe)", 2),
    },
)
