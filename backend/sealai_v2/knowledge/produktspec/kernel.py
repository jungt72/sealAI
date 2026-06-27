"""Produktspec resolution engine (Konzept v2 §4/§9/§12). DETERMINISTIC: criticality → completeness gate →
constraint-resolution (disqualify > defer > muss > kann > conflict) → reifegrad-gating. Family-specific
logic lives in the rules (DATA) + the FamilyKernel meta — the engine is the shared Family-Kernel-Contract.
No L1, no capability data: the spec is a pure function of (Fall, neutral rules)."""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.knowledge.produktspec.contracts import (
    Auswahlregel,
    Bedingung,
    Fall,
    KandidatenSpec,
    Kritikalitaet,
    MaßAngabe,
    Regeltyp,
    SizeType,
    darf_konkret_empfehlen,
)

# Konzept v2 §10 — applications that must NOT receive a candidate spec; escalate to expert review.
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
    "pressure equipment",
    "wasserstoff",
    " h2",
    "sco2",
    "sicherheitskritisch",
    "kerntechnik",
    "nuklear",
)


@dataclass(frozen=True)
class FamilyKernel:
    familie: str
    norm: str
    required_inputs: tuple[str, ...]
    rules: tuple[Auswahlregel, ...]
    bauform_meta: dict  # bauform-key -> (din_bezeichnung: str, lippen: int)


def _absent(fall: Fall, feld: str) -> bool:
    v = getattr(fall, feld, None)
    return v is None or v == ""


def _eval(b: Bedingung, fall: Fall) -> bool:
    v = getattr(fall, b.feld, None)
    if b.op == "present":
        return not _absent(fall, b.feld)
    if b.op == "absent":
        return _absent(fall, b.feld)
    if v is None:
        return False
    if b.op == "contains":
        return str(b.wert).lower() in str(v).lower()
    if b.op == "eq":
        return v == b.wert
    try:
        if b.op == "gt":
            return float(v) > float(b.wert)  # type: ignore[arg-type]
        if b.op == "lt":
            return float(v) < float(b.wert)  # type: ignore[arg-type]
        if b.op == "ge":
            return float(v) >= float(b.wert)  # type: ignore[arg-type]
        if b.op == "le":
            return float(v) <= float(b.wert)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return False


def _fires(r: Auswahlregel, fall: Fall) -> bool:
    return all(_eval(b, fall) for b in r.bedingungen)


def classify_kritikalitaet(fall: Fall) -> Kritikalitaet:
    text = f"{fall.medium} {fall.rohtext} {fall.gehaeuse}".lower()
    if any(k in text for k in _ESKALATION):
        return Kritikalitaet.HIGH_RISK
    if _absent(fall, "medium"):
        return Kritikalitaet.CAUTION  # unknown medium → material cannot be asserted
    return Kritikalitaet.NORMAL


def _escalation_spec(familie: str, krit: Kritikalitaet) -> KandidatenSpec:
    return KandidatenSpec(
        familie=familie,
        kritikalitaet=krit,
        bauform_din=None,
        werkstoff=None,
        lippen=None,
        masse=(),
        begruendung=(),
        varianten=(),
        konflikte=(),
        offene_punkte=(
            "Kritische/regulatorisch sensible Anwendung — bitte mit Fachverantwortlichem und Hersteller klären.",
        ),
        defer_gruende=(
            f"Kritikalität {krit.value}: keine Kandidaten-Spezifikation; Fachprüfung erforderlich.",
        ),
        teil_screening=True,
        freigegeben=False,
    )


def resolve(fall: Fall, kernel: FamilyKernel) -> KandidatenSpec:
    krit = classify_kritikalitaet(fall)
    if krit in (Kritikalitaet.HIGH_RISK, Kritikalitaet.OUT_OF_SCOPE):
        return _escalation_spec(kernel.familie, krit)

    fehlende = [f for f in kernel.required_inputs if _absent(fall, f)]
    offene: list[str] = []
    defer: list[str] = []
    begruendung: list[str] = []
    varianten: list[str] = []
    konflikte: list[str] = []
    quellen: list[str] = []
    konkret_reifegrade: list = []

    # 1) Disqualify (Eignungsgrenzen) — schlägt alles.
    disq = [
        r for r in kernel.rules if r.regeltyp is Regeltyp.GRENZE and _fires(r, fall)
    ]
    for r in disq:
        defer.append(f"{r.konsequenz} (Regel {r.id}, {r.normbezug}): {r.provenance}")
        quellen.append(r.id)
    standard_disqualifiziert = bool(disq)

    # 2) Bauform-Kandidaten (Constraint-Resolution, KEIN Ranking).
    bauform: str | None = None
    lippen: int | None = None
    if standard_disqualifiziert:
        offene.append(
            "Standard-Bauform disqualifiziert — andere Dichtungsfamilie mit dem Hersteller prüfen."
        )
    else:
        form_hits = [
            r for r in kernel.rules if r.regeltyp is Regeltyp.FORM and _fires(r, fall)
        ]
        uniq: dict[str, Auswahlregel] = {}
        for r in form_hits:
            uniq.setdefault(r.konsequenz.split(":", 1)[1], r)
        if len(uniq) == 1:
            bf, r = next(iter(uniq.items()))
            bez, lip = kernel.bauform_meta.get(bf, (bf, None))
            bauform, lippen = bez, lip
            begruendung.append(
                f"Bauform {bf}: Regel {r.id} ({r.normbezug}) [{r.reifegrad.value}]"
            )
            quellen.append(r.id)
            konkret_reifegrade.append(r.reifegrad)
        elif len(uniq) > 1:
            for bf, r in uniq.items():
                bez, _ = kernel.bauform_meta.get(bf, (bf, None))
                varianten.append(f"{bez} (Regel {r.id})")
                quellen.append(r.id)
            konflikte.append(
                "Mehrere Bauformen möglich — Entscheidung offen (Constraint-Resolution, kein Ranking)."
            )
            offene.append(
                "Bauform-Entscheidung: weitere Inputs (Gehäuse/Oberfläche/Montage) erforderlich."
            )

    # 3) Werkstoff — nur wenn Medium UND Temperatur vorliegen (sonst Defer).
    werkstoff: str | None = None
    if not _absent(fall, "medium") and not _absent(fall, "temperatur_c"):
        ausgeschlossen = {
            r.konsequenz.split(":")[-1]
            for r in kernel.rules
            if r.regeltyp is Regeltyp.NEGATIV and _fires(r, fall)
        }
        uniqw: dict[str, Auswahlregel] = {}
        for r in kernel.rules:
            if r.regeltyp is Regeltyp.WERKSTOFF and _fires(r, fall):
                wk = r.konsequenz.split(":", 1)[1]
                if wk not in ausgeschlossen:
                    uniqw.setdefault(wk, r)
        if len(uniqw) == 1:
            wk, r = next(iter(uniqw.items()))
            werkstoff = wk
            begruendung.append(
                f"Werkstoff {wk}: Regel {r.id} ({r.normbezug}) [{r.reifegrad.value}]"
            )
            quellen.append(r.id)
            konkret_reifegrade.append(r.reifegrad)
        elif len(uniqw) > 1:
            for wk, r in uniqw.items():
                varianten.append(f"Werkstoff {wk} (Regel {r.id})")
                quellen.append(r.id)
            konflikte.append(
                "Mehrere Werkstoffe möglich — Medium/Temperatur im Detail klären."
            )
    else:
        offene.append("Werkstoff nicht ableitbar — Medium und/oder Temperatur fehlen.")

    for f in fehlende:
        offene.append(f"Pflichteingabe fehlt: {f}.")

    # 4) Maße: Welle = OBSERVED (User); Dichtungs-OD/Breite werden NICHT fabriziert (DIN-Copyright + Pseudo-
    #    Präzision) → bleiben offener Punkt.
    masse: list[MaßAngabe] = []
    if fall.welle_d_mm is not None:
        masse.append(MaßAngabe("welle_d", fall.welle_d_mm, "mm", SizeType.OBSERVED))
    offene.append(
        "Dichtungs-Außen-Ø und Breite gegen DIN + Herstellerdatenblatt verifizieren (nicht abgeleitet)."
    )

    # 5) Reifegrad-Gating: nichts Konkretes ist expert_signed → Kandidat, NICHT freigegeben (Konzept v2 §8).
    konkret_signed = any(darf_konkret_empfehlen(rg) for rg in konkret_reifegrade)
    if (bauform or werkstoff) and not konkret_signed:
        defer.append(
            "Wissensstand 'reviewed_internal' — Kandidat ohne technische Freigabe; Fachprüfung (expert_signed) ausstehend."
        )

    teil = (
        bool(fehlende)
        or bool(konflikte)
        or standard_disqualifiziert
        or (bauform is None and werkstoff is None)
    )
    return KandidatenSpec(
        familie=kernel.familie,
        kritikalitaet=krit,
        bauform_din=bauform,
        werkstoff=werkstoff,
        lippen=lippen,
        masse=tuple(masse),
        begruendung=tuple(begruendung),
        varianten=tuple(varianten),
        konflikte=tuple(konflikte),
        offene_punkte=tuple(offene),
        defer_gruende=tuple(defer),
        teil_screening=teil,
        freigegeben=False,  # structural invariant in the prototype
        quellen=tuple(quellen),
    )
