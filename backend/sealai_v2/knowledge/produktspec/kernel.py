"""Produktspec v3.1 engine (Konzept v3.1). Deterministic, axis-based, with the RED guards enforced by the
type model: max level L2, no single material from free text, never a final DIN code. RWDR is the one
reference family (Family-Kernel-Contract = the resolve_* functions). No L1/capability data."""

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


def classify_envelope(fall: Fall) -> EnvelopeBand:
    p = fall.druck_bar if fall.druck_bar is not None else 0.0
    v = speed_ms(fall)
    medium_exakt = fall.medium_source == MediumSource.EXACT and bool(fall.medium_class)
    lube_ok = fall.schmierung_ok is True
    clean = fall.verschmutzung is False
    vented = (fall.belueftet is True) or (p == 0.0)
    # RED — outside standard scope
    if p > 0.5 or fall.druck_puls or fall.vakuum:
        return EnvelopeBand.RED
    if (
        p > 0.0 and fall.axiale_sicherung_ok is not True
    ):  # Druckdifferenz ohne bestätigte Sicherung
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
    # GREEN (v3.1: green_extended deckt den 8–12 m/s-Standardfall mit Prüfpunkt ab)
    t = fall.temperatur_c
    if v <= 8.0 and t <= 80.0:
        return EnvelopeBand.GREEN_BASE
    if v <= 12.0 and t <= 100.0:
        return EnvelopeBand.GREEN_EXTENDED
    return EnvelopeBand.YELLOW


def _resolve_material_candidates(fall: Fall) -> tuple[list[str], list[str]]:
    mc = fall.medium_class.lower()
    text = f"{fall.medium} {fall.rohtext}".lower()
    if any(w in text for w in _AGGRESSIV) and fall.medium_source != MediumSource.EXACT:
        return [], [
            "N-AGGRESSIVE-UNCLASSIFIED: exaktes Medium/SDS nötig — kein Elastomer-Kandidat"
        ]
    if not mc and not fall.medium:
        return [], ["Medium fehlt — kein Werkstoff ableitbar"]
    t = fall.temperatur_c
    cands: list[tuple[str, str]] = []
    hydrocarbon = mc in (
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
        "hfd",
    ) or ("öl" in mc and "silikon" not in mc)
    if hydrocarbon and t is not None:
        if t <= 100:
            cands.append(("NBR", "W-NBR"))
        if t <= 150:
            cands.append(("HNBR", "W-HNBR"))
        if 100 < t <= 200:
            cands.append(("FKM", "W-FKM"))
    if "wasser" in mc or mc in (
        "dampf",
        "glykol_bremsfluessigkeit",
        "glykol",
        "wasser_glykol",
        "polar",
    ):
        if t is None or t <= 120:
            cands.append(("EPDM", "W-EPDM"))
    if "silikon" in mc:
        cands.append(("EPDM", "W-EPDM-SILICONE"))
    if (t is not None and t > 200) or fall.schmierung_ok is False:
        cands.append(("PTFE", "ESC-CHEM"))
    prov: list[str] = []
    excl: set[str] = set()
    if hydrocarbon:
        excl.add("EPDM")  # N-EPDM-HC (medium_class-basiert, NICHT Keyword „Öl")
    if "dampf" in mc or "heisswasser" in mc:
        excl.add("FKM")  # N-FKM-STEAM
    if mc in ("amin", "lauge", "ammoniak"):
        excl.add("FKM")  # N-FKM-AMINE
    if mc == "glykol_bremsfluessigkeit":
        excl.update({"NBR", "HNBR"})  # N-NBR-BRAKE
    if mc == "hfd":
        excl.update({"NBR", "HNBR"})  # W-NBR-HYDRAULIC: HFD ausschließen
        prov.append("W-NBR-HYDRAULIC: HFD → NBR/HNBR ausgeschlossen")
    if mc == "hfc":
        prov.append("W-NBR-HYDRAULIC: HFC → NBR nur Low-Temp/spezifisch, sonst Defer")
    res: list[str] = []
    for m, rid in cands:
        if m not in excl and m not in res:
            res.append(m)
            prov.append(f"{rid}:{m}")
    if not res:
        prov.append(
            "Kein eindeutiger Werkstoff-Kandidat — Medienklasse/Temperatur prüfen"
        )
    return res, prov


def _resolve_lip(fall: Fall) -> Axis:
    if fall.verschmutzung is True:
        return Axis(
            "lip",
            "main+dust_lip",
            AxisStatus.OK,
            ("LIP-AS: Staublippe (Fettfilm nötig)",),
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
    if "stahl" in m or "präzise" in m or "praezise" in m:
        return Axis("od", "metal_od", AxisStatus.OK, ("OD-METAL",))
    # Unknown housing is a CHECKPOINT (ask), not a hard block — a clean green case stays L2 with a Prüfpunkt.
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
            "retaining_geometry_required",
            AxisStatus.GATE_BLOCKED,
            ("F-PRESSURE: Druckdichtung/axiale Sicherung",),
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
    # Speed is already banded by the envelope (green capped at 12 m/s); the hard shaft gate is for
    # contamination/pressure, where wear/blow-out risk makes unknown hardness unacceptable.
    if hard_unknown and (fall.verschmutzung is True or (fall.druck_bar or 0) > 0):
        return Axis(
            "shaft",
            None,
            AxisStatus.GATE_BLOCKED,
            ("S-HRC-GATE: Härte/Wellenzustand unbekannt bei Schmutz/Druck",),
        )
    if hard_unknown and v > 4:
        return Axis(
            "shaft",
            "haerte_offen",
            AxisStatus.OPEN_VERIFICATION,
            ("S-HRC-OPEN: Wellenhärte verifizieren (≥45/55 HRC)",),
        )
    return Axis("shaft", "ok", AxisStatus.OK, ())


def _din_label(lip: Axis, od: Axis, pressure: Axis, mats: list[str]) -> str:
    return (
        "DIN-3760-orientierter Kandidatenraum: "
        f"Lippe={lip.value or 'offen'}, OD={od.value or 'offen (Gehäuse erfragen)'}, "
        f"Druck={pressure.value or 'offen'}, Werkstoff-Kandidaten={'/'.join(mats) or '—'}"
    )


def _escalation(krit: Kritikalitaet) -> KandidatenSpec:
    return KandidatenSpec(
        response_level=ResponseLevel.L0_ESCALATION,
        envelope_band=None,
        kritikalitaet=krit,
        axes=(),
        material_candidate_set=(),
        material_single=None,
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


def _failure_mode(fall: Fall) -> KandidatenSpec:
    return KandidatenSpec(
        response_level=ResponseLevel.L1_CANDIDATE_SPACE,
        envelope_band=None,
        kritikalitaet=Kritikalitaet.CAUTION,
        axes=(),
        material_candidate_set=(),
        material_single=None,
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
        return _failure_mode(fall)

    band = classify_envelope(fall)
    mats, mat_prov = _resolve_material_candidates(fall)
    lip, od = _resolve_lip(fall), _resolve_od(fall)
    pressure, shaft = _resolve_pressure(band), _resolve_shaft(fall)
    material_axis = Axis(
        "material", None, AxisStatus.OK if mats else AxisStatus.UNKNOWN, tuple(mat_prov)
    )
    axes = (lip, od, pressure, shaft, material_axis)

    material_exact = fall.medium_source == MediumSource.EXACT and bool(
        fall.medium_class
    )
    # L2 is blocked by hard gates / conflicts / a missing core axis (lip or material) — NOT by
    # open_verification checkpoints (OD/shaft), which a clean green case is allowed to carry.
    axes_block = (
        any(a.status in (AxisStatus.CONFLICT, AxisStatus.GATE_BLOCKED) for a in axes)
        or lip.status is AxisStatus.UNKNOWN
        or material_axis.status is AxisStatus.UNKNOWN
    )
    green = band in (EnvelopeBand.GREEN_BASE, EnvelopeBand.GREEN_EXTENDED)
    # G1/G2: L2 only for a clean green case from an EXACT medium with resolved axes.
    level = (
        ResponseLevel.L2_SCREENING_CANDIDATE
        if (green and material_exact and mats and not axes_block)
        else ResponseLevel.L1_CANDIDATE_SPACE
    )
    # G3: never a final DIN code; a candidate LABEL only at L2.
    din_label = (
        _din_label(lip, od, pressure, mats)
        if level == ResponseLevel.L2_SCREENING_CANDIDATE
        else None
    )

    open_verif = tuple(
        b
        for a in axes
        if a.status is AxisStatus.OPEN_VERIFICATION
        for b in a.begruendung
    )
    defer = [
        b for a in axes if a.status is AxisStatus.GATE_BLOCKED for b in a.begruendung
    ]
    if band in (EnvelopeBand.ORANGE, EnvelopeBand.RED):
        defer.append(
            f"Envelope {band.value}: außerhalb gesichertem Screening — Frageliste/Spezial."
        )
    if not material_exact:
        defer.append(
            "Medium nicht exakt (Freitext) → nur Werkstoff-Kandidatenraum, kein Einzelwerkstoff (max L1)."
        )
    if material_axis.status is AxisStatus.UNKNOWN:
        defer.extend(
            material_axis.begruendung
        )  # „kein Werkstoff ableitbar" / N-AGGRESSIVE = Defer-Grund
    offene = [
        b
        for a in axes
        if a.status is AxisStatus.UNKNOWN and a.name != "material"
        for b in a.begruendung
    ]
    offene.append(
        "Dichtungs-Außen-Ø/Breite + Form gegen DIN + Datenblatt verifizieren (nicht abgeleitet)."
    )
    quellen = tuple(dict.fromkeys(b for a in axes for b in a.begruendung))

    return KandidatenSpec(
        response_level=level,
        envelope_band=band,
        kritikalitaet=krit,
        axes=axes,
        material_candidate_set=tuple(mats),
        material_single=None,
        din_candidate_label=din_label,
        final_design_code=None,
        defer_gruende=tuple(defer),
        open_verifications=open_verif,
        offene_punkte=tuple(offene),
        freigegeben=False,
        quellen=quellen,
    )


def render_texts(spec: KandidatenSpec) -> str:
    """All user-facing strings — for the no-forbidden-words schranke."""
    parts = [
        spec.din_candidate_label or "",
        spec.geltungsrahmen,
        *spec.material_candidate_set,
    ]
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
