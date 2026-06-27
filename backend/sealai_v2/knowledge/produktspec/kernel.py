"""Produktspec v3.1+ engine (Konzept v3.1 + Fachreview-Patches A6/A9/A10/B4/D2/A1/A5/A8). Deterministic,
axis-based, RED guards (max L2, no single material from free text, never a final DIN code). Material =
typed MaterialResult (never a bare 'empty'); primary/alternatives/escalation/excluded + reason/next_question."""

from __future__ import annotations

import math

from sealai_v2.knowledge.produktspec.contracts import (
    VERBOTENE_WOERTER,
    ApplicationMode,
    Axis,
    AxisStatus,
    EnvelopeBand,
    Fall,
    KandidatenSpec,
    Kritikalitaet,
    MaterialKind,
    MaterialResult,
    MediumSource,
    ResponseLevel,
)

_ESKALATION = (
    "atex",
    "ex-schutz",
    "explosion",
    "lebensmittel",
    "food",
    "pharma",
    "fda",
    "eu 1935",
    "druckgerät",
    "druckgeraet",
    "wasserstoff",
    " h2",
    "sco2",
    "sicherheitskritisch",
    "kerntechnik",
)
_AGGRESSIV = ("aggressiv", "chemie", "reiniger", "säure", "lauge", "lösemittel")
_HYDROCARBON = (
    "mineraloel",
    "mineralöl",
    "kw_fett",
    "fett",
    "kraftstoff",
    "diesel",
    "benzin",
    "pao",
    "aromat_kw",
    "hlp",
    "hl",
)
_FUEL = ("kraftstoff", "diesel", "benzin", "aromat_kw")


def speed_ms(fall: Fall) -> float | None:
    if fall.geschwindigkeit_ms is not None:
        return fall.geschwindigkeit_ms
    if fall.drehzahl_rpm is not None and fall.welle_d_mm is not None:
        return math.pi * fall.welle_d_mm * fall.drehzahl_rpm / 60000.0
    return None


def classify_kritikalitaet(fall: Fall) -> Kritikalitaet:
    text = f"{fall.medium} {fall.rohtext} {fall.gehaeuse}".lower()
    if any(k in text for k in _ESKALATION):
        return Kritikalitaet.HIGH_RISK
    if fall.medium == "" and fall.medium_class == "":
        return Kritikalitaet.CAUTION
    return Kritikalitaet.NORMAL


def _contamination_managed(fall: Fall) -> bool:
    # PATCH-4 (D2): Schmutz ist beherrschbar (→ AS), wenn Härte ≥55 HRC, v≤4 m/s, kein Leckagefall.
    return (
        fall.verschmutzung is True
        and fall.welle_haerte_hrc is not None
        and fall.welle_haerte_hrc >= 55
        and (speed_ms(fall) or 0.0) <= 4.0
    )


def classify_envelope(fall: Fall) -> EnvelopeBand:
    p = fall.druck_bar if fall.druck_bar is not None else 0.0
    v = speed_ms(fall)
    medium_exakt = fall.medium_source == MediumSource.EXACT and bool(fall.medium_class)
    lube_ok = fall.schmierung_ok is True
    clean = (fall.verschmutzung is False) or _contamination_managed(fall)
    vented = (fall.belueftet is True) or (p == 0.0)
    # RED — PATCH-3 (B4): >= 0,5 bar konservativ außer Scope.
    if p >= 0.5 or fall.druck_puls or fall.vakuum:
        return EnvelopeBand.RED
    if p > 0.0 and fall.axiale_sicherung_ok is not True:
        return EnvelopeBand.RED
    # ORANGE — defer
    if v is None or v > 12.0:
        return EnvelopeBand.ORANGE
    if p > 0.2 or not lube_ok or not medium_exakt or fall.temperatur_c is None:
        return EnvelopeBand.ORANGE
    if not (vented and clean):
        return EnvelopeBand.ORANGE
    # YELLOW
    if 0.05 < p <= 0.2:
        return EnvelopeBand.YELLOW
    # GREEN
    t = fall.temperatur_c
    if v <= 8.0 and t <= 80.0:
        return EnvelopeBand.GREEN_BASE
    if v <= 12.0 and t <= 100.0:
        return EnvelopeBand.GREEN_EXTENDED
    return EnvelopeBand.YELLOW


def _resolve_material(fall: Fall) -> MaterialResult:
    mc = fall.medium_class.lower()
    text = f"{fall.medium} {fall.rohtext}".lower()
    exact = fall.medium_source == MediumSource.EXACT and bool(mc)
    if any(w in text for w in _AGGRESSIV) and not exact:
        return MaterialResult(
            MaterialKind.EMPTY_UNKNOWN,
            reason_codes=("N-AGGRESSIVE-UNCLASSIFIED",),
            next_question=(
                "Exaktes Medium/Konzentration/SDS — kein Elastomer-Kandidat ohne Stoff",
            ),
        )
    if not exact:
        return MaterialResult(
            MaterialKind.EMPTY_UNKNOWN,
            reason_codes=("Freitext/unbekannt",),
            next_question=("Exakte Medienbezeichnung / Trade-Name / SDS erforderlich",),
        )
    t = fall.temperatur_c
    # PATCH-1 (A6) Dampf/Heißwasser >120°C → Spezialeskalation, NICHT leer.
    if ("dampf" in mc or "heisswasser" in mc) and (t is None or t > 120):
        return MaterialResult(
            MaterialKind.SPECIAL_ESCALATION,
            escalation=("EPDM-Sondergrade für Dampf", "PTFE/Sonderdichtung"),
            excluded=("FKM",),
            reason_codes=("W-STEAM-HIGH",),
            next_question=(
                "Dampfart, Druck, Kondensat, Geschwindigkeit, Schmierung — Herstellerprüfung",
            ),
        )
    # PATCH-6 (A10) HFD → fire-resistant Spezialeskalation, NICHT leer.
    if mc == "hfd":
        return MaterialResult(
            MaterialKind.SPECIAL_ESCALATION,
            escalation=("typabhängig FKM/EPDM/PTFE",),
            excluded=("NBR", "HNBR"),
            reason_codes=("SPECIAL-FIRE-RESISTANT-HYDRAULIC",),
            next_question=("HFD-Subtyp / SDS",),
        )
    # PATCH-2 (A9) HFC → NBR nur low-temp, sonst Defer (kein Code-Loch).
    if mc == "hfc":
        if t is not None and t <= 50:
            return MaterialResult(
                MaterialKind.CANDIDATE_SET,
                primary=("NBR",),
                reason_codes=("W-NBR-HFC-LOWTEMP",),
                validation_required=True,  # additiv-/glykolabhängig → max L1
                next_question=(
                    "HFC: nur low-temp/spezifisch validieren (wasser-glykol, additivabhängig)",
                ),
            )
        return MaterialResult(
            MaterialKind.EMPTY_UNKNOWN,
            reason_codes=("W-NBR-HYDRAULIC",),
            next_question=("HFC > 50°C: exaktes Fluid / SDS",),
        )
    hydrocarbon = mc in _HYDROCARBON or ("öl" in mc and "silikon" not in mc)
    if hydrocarbon:
        if t is None:
            return MaterialResult(
                MaterialKind.EMPTY_UNKNOWN,
                reason_codes=("Temperatur fehlt",),
                next_question=("Dauertemperatur angeben",),
            )
        if t > 200:  # A4
            return MaterialResult(
                MaterialKind.SPECIAL_ESCALATION,
                escalation=("PTFE", "Spezial-FKM/Sonderdesign"),
                reason_codes=("SPECIAL-HIGH-TEMP",),
                next_question=("Kein DIN-A/AS; Herstellerprüfung",),
            )
        primary: list[str] = []
        alt: list[str] = []
        if t <= 100:  # A1: NBR primary, HNBR Upgrade
            primary.append("NBR")
            alt.append("HNBR")
        elif t <= 150:  # A2: Lücke NBR↔FKM
            primary.append("HNBR")
            alt.append("FKM")
        if 100 < t <= 200 and "FKM" not in primary and "FKM" not in alt:
            primary.append("FKM")
        if mc in _FUEL and "FKM" not in primary and "FKM" not in alt:  # PATCH-5 (A8)
            alt.append("FKM")
        return MaterialResult(
            MaterialKind.CANDIDATE_SET,
            primary=tuple(primary),
            alternatives=tuple(alt),
            excluded=("EPDM",),
            reason_codes=("W-NBR/HNBR/FKM",),
        )
    if "wasser" in mc or mc in (
        "glykol_bremsfluessigkeit",
        "glykol",
        "wasser_glykol",
        "polar",
    ):
        nq = []
        if "wasser" in mc and "glykol" not in mc:  # PATCH-7 (A5)
            nq.append(
                "water_lubricity_caution: Wasser ist ein schlechtes Schmiermedium für RWDR"
            )
        return MaterialResult(
            MaterialKind.CANDIDATE_SET,
            primary=("EPDM",),
            excluded=("NBR", "HNBR", "FKM"),
            reason_codes=("W-EPDM",),
            next_question=tuple(nq),
        )
    if (
        "silikon" in mc
    ):  # A11 — EPDM-Kandidat (kein Keyword-Ausschluss), aber bestätigen
        return MaterialResult(
            MaterialKind.CANDIDATE_SET,
            primary=("EPDM",),
            reason_codes=("W-EPDM-SILICONE",),
            next_question=("Exaktes Silikonöl/-fett bestätigen",),
        )
    return MaterialResult(
        MaterialKind.EMPTY_UNKNOWN,
        reason_codes=("Medienklasse/Temperatur prüfen",),
        next_question=("Exakte Medienklasse + Temperatur",),
    )


def _resolve_lip(fall: Fall) -> Axis:
    if fall.verschmutzung is True:
        return Axis(
            "lip",
            "main+dust_lip",
            AxisStatus.OK,
            ("LIP-AS: Staublippe (Fettfilm zwischen Lippen prüfen)",),
        )
    if fall.verschmutzung is False:
        return Axis("lip", "main_lip", AxisStatus.OK, ("LIP-A",))
    return Axis("lip", None, AxisStatus.UNKNOWN, ("Verschmutzung unbekannt",))


def _resolve_od(fall: Fall) -> Axis:
    m = f"{fall.gehaeuse_material} {fall.gehaeuse}".lower()
    if any(w in m for w in ("alu", "leichtmetall", "geteilt", "rau", "verschlissen")):
        return Axis(
            "od", "elastomer_covered_od", AxisStatus.OK, ("OD-ELASTOMER (verifiziert)",)
        )
    if (
        "stahl" in m or "präzise" in m or "praezise" in m
    ):  # PATCH-8 (C4): Kandidat, nicht Pflicht
        return Axis("od", "metal_od (Kandidat)", AxisStatus.OK, ("OD-METAL-Kandidat",))
    return Axis(
        "od",
        None,
        AxisStatus.OPEN_VERIFICATION,
        ("OD-UNKNOWN: Gehäuse/Toleranz/Rauheit erfragen",),
    )


def _resolve_pressure(band: EnvelopeBand) -> Axis:
    if band == EnvelopeBand.RED:
        return Axis(
            "pressure",
            "outside_standard_scope",
            AxisStatus.GATE_BLOCKED,
            ("G-STD-PRESSURE: Druckprofil/Haltegeometrie/Herstellerprüfung",),
        )
    return Axis("pressure", "pressureless_low", AxisStatus.OK, ())


def _resolve_shaft(fall: Fall) -> Axis:
    v = speed_ms(fall) or 0.0
    hard_unknown = fall.welle_haerte_hrc is None
    if fall.welle_drall is True:
        return Axis(
            "shaft",
            "drall",
            AxisStatus.GATE_BLOCKED,
            (
                "N-SHAFT-LEAD-PUMPING: Wellendrall → Leckage unabhängig vom Dichtungstyp",
            ),
        )
    if hard_unknown and (fall.verschmutzung is True or (fall.druck_bar or 0) > 0):
        return Axis(
            "shaft",
            None,
            AxisStatus.GATE_BLOCKED,
            ("S-HRC-GATE: Härte/Wellenzustand unbekannt bei Schmutz/Druck",),
        )
    if (
        fall.verschmutzung is True
    ):  # PATCH-4: Schmutz (mit ausreichender Härte) → Prüfpunkt, kein Block
        return Axis(
            "shaft",
            "haerte_ok_offen",
            AxisStatus.OPEN_VERIFICATION,
            ("S-HRC-DIRT: Härte ≥55 HRC + AS/Fettfilm prüfen",),
        )
    if hard_unknown and v > 4:
        return Axis(
            "shaft",
            "haerte_offen",
            AxisStatus.OPEN_VERIFICATION,
            ("S-HRC-OPEN: Wellenhärte verifizieren (≥45/55 HRC)",),
        )
    return Axis("shaft", "ok", AxisStatus.OK, ())


def _din_label(lip: Axis, od: Axis, pressure: Axis, primary: tuple[str, ...]) -> str:
    return (
        "DIN-3760-orientierter Kandidatenraum: "
        f"Lippe={lip.value or 'offen'}, OD={od.value or 'offen (Gehäuse erfragen)'}, "
        f"Druck={pressure.value or 'offen'}, Werkstoff-Primär={'/'.join(primary) or '—'}"
    )


def _spec(level, band, krit, axes, material, din_label, defer, openv, offene, quellen):
    return KandidatenSpec(
        response_level=level,
        envelope_band=band,
        kritikalitaet=krit,
        axes=axes,
        material=material,
        din_candidate_label=din_label,
        final_design_code=None,
        defer_gruende=tuple(defer),
        open_verifications=tuple(openv),
        offene_punkte=tuple(offene),
        freigegeben=False,
        quellen=tuple(quellen),
    )


def _escalation(krit: Kritikalitaet) -> KandidatenSpec:
    return KandidatenSpec(
        response_level=ResponseLevel.L0_ESCALATION,
        envelope_band=None,
        kritikalitaet=krit,
        axes=(),
        material=MaterialResult(MaterialKind.EMPTY_UNKNOWN),
        din_candidate_label=None,
        final_design_code=None,
        defer_gruende=(
            f"Kritikalität {krit.value}: keine Spezifikation; Fachprüfung erforderlich.",
        ),
        offene_punkte=(
            "Kritische/regulatorisch sensible Anwendung — mit Fachverantwortlichem/Hersteller klären.",
        ),
        freigegeben=False,
    )


def _failure_mode() -> KandidatenSpec:
    return KandidatenSpec(
        response_level=ResponseLevel.L1_CANDIDATE_SPACE,
        envelope_band=None,
        kritikalitaet=Kritikalitaet.CAUTION,
        axes=(),
        material=MaterialResult(MaterialKind.EMPTY_UNKNOWN),
        din_candidate_label=None,
        final_design_code=None,
        defer_gruende=(
            "Leckage/Ausfall → Fehlerursache VOR Werkstoff-/Bauformwechsel.",
        ),
        failure_mode_checklist=(
            "Wellenoberfläche/Drall (Helix) prüfen",
            "Rundlauf/Fluchtung/Lagerluft",
            "Montage + Einbaurichtung",
            "Trockenanlauf",
            "Entlüfter/Überdruck im Gehäuse",
            "Lauffläche/Einlaufspur/Korrosion",
        ),
        offene_punkte=(
            "Kein Produkttausch als Primärantwort bei Leckage/Frühausfall.",
        ),
        freigegeben=False,
    )


def resolve(fall: Fall) -> KandidatenSpec:
    krit = classify_kritikalitaet(fall)
    if krit in (Kritikalitaet.HIGH_RISK, Kritikalitaet.OUT_OF_SCOPE):
        return _escalation(krit)
    if fall.application_mode in (
        ApplicationMode.LEAKAGE_FAILURE,
        ApplicationMode.PREMATURE_FAILURE,
    ):
        return _failure_mode()

    band = classify_envelope(fall)
    material = _resolve_material(fall)
    lip, od = _resolve_lip(fall), _resolve_od(fall)
    pressure, shaft = _resolve_pressure(band), _resolve_shaft(fall)
    mat_status = (
        AxisStatus.OK
        if material.kind is MaterialKind.CANDIDATE_SET and material.primary
        else AxisStatus.OPEN_VERIFICATION
        if material.kind is MaterialKind.SPECIAL_ESCALATION
        else AxisStatus.UNKNOWN
    )
    material_axis = Axis(
        "material",
        "/".join(material.primary) or None,
        mat_status,
        material.reason_codes + material.next_question,
    )
    axes = (lip, od, pressure, shaft, material_axis)

    material_exact = fall.medium_source == MediumSource.EXACT and bool(
        fall.medium_class
    )
    axes_block = (
        any(a.status in (AxisStatus.CONFLICT, AxisStatus.GATE_BLOCKED) for a in axes)
        or lip.status is AxisStatus.UNKNOWN
        or material_axis.status is AxisStatus.UNKNOWN
    )
    green = band in (EnvelopeBand.GREEN_BASE, EnvelopeBand.GREEN_EXTENDED)
    l2 = (
        green
        and material_exact
        and material.kind is MaterialKind.CANDIDATE_SET
        and material.primary
        and not material.validation_required
        and not axes_block
    )
    level = (
        ResponseLevel.L2_SCREENING_CANDIDATE if l2 else ResponseLevel.L1_CANDIDATE_SPACE
    )
    din_label = _din_label(lip, od, pressure, material.primary) if l2 else None

    openv = list(
        b
        for a in axes
        if a.status is AxisStatus.OPEN_VERIFICATION
        for b in a.begruendung
    )
    openv.extend(material.next_question)
    defer = [
        b for a in axes if a.status is AxisStatus.GATE_BLOCKED for b in a.begruendung
    ]
    if material.kind is MaterialKind.SPECIAL_ESCALATION:
        defer.append(
            "Sonderwerkstoff-Eskalation: "
            + "/".join(material.escalation)
            + " — kein DIN-A/AS, Herstellerprüfung."
        )
    if material.kind in (MaterialKind.EMPTY_UNKNOWN, MaterialKind.EMPTY_EXCLUDED):
        defer.extend(material.reason_codes)
    if band in (EnvelopeBand.ORANGE, EnvelopeBand.RED):
        defer.append(
            f"Envelope {band.value}: außerhalb gesichertem Screening — Frageliste/Spezial."
        )
    if not material_exact:
        defer.append("Medium nicht exakt (Freitext) → kein Einzelwerkstoff (max L1).")
    offene = [
        b
        for a in axes
        if a.status is AxisStatus.UNKNOWN and a.name != "material"
        for b in a.begruendung
    ]
    if material.excluded:
        offene.append("Ausgeschlossen: " + "/".join(material.excluded))
    offene.append(
        "Dichtungs-Außen-Ø/Breite + Form gegen DIN + Datenblatt verifizieren (nicht abgeleitet)."
    )
    quellen = list(dict.fromkeys(b for a in axes for b in a.begruendung))
    return _spec(
        level, band, krit, axes, material, din_label, defer, openv, offene, quellen
    )


def render_texts(spec: KandidatenSpec) -> str:
    parts = [spec.din_candidate_label or "", spec.geltungsrahmen]
    parts += (
        list(spec.material.primary)
        + list(spec.material.alternatives)
        + list(spec.material.escalation)
    )
    parts += list(spec.material.next_question) + list(spec.material.reason_codes)
    for seq in (
        spec.defer_gruende,
        spec.open_verifications,
        spec.offene_punkte,
        spec.failure_mode_checklist,
    ):
        parts.extend(seq)
    for a in spec.axes:
        parts.extend(a.begruendung)
    return " ".join(parts).lower()


__all__ = [
    "resolve",
    "classify_envelope",
    "render_texts",
    "speed_ms",
    "VERBOTENE_WOERTER",
]
