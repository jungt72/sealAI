"""Echte Fallbeispiele als rote Regressionsschranken (Konzept v3.1 — „Eval-Traps gegen echte Fallbeispiele").
Testet ENGINE-VERHALTEN (richtige Antwortstufe / sicher deferieren / nicht überblocken / nie über-claimen),
NICHT die domänen-finale Antwort. Speeds aus v = pi*d*n/60000. Stand: 16/17 erwartungsgemäß; 1 offenes
Finding (A2b, Schmutz+AS+Härte) ist als Domänen-Kalibrierung für die Fachsignatur markiert, nicht gepinnt."""

from __future__ import annotations

from sealai_v2.knowledge.produktspec.contracts import (
    ApplicationMode as AM,
    Fall,
    MediumSource as MS,
    ResponseLevel as RL,
)
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation as K


def _clean_known(**over) -> Fall:
    base = dict(
        medium="Mineralöl",
        medium_class="mineraloel",
        medium_source=MS.EXACT,
        temperatur_c=70.0,
        druck_bar=0.0,
        geschwindigkeit_ms=3.0,
        welle_d_mm=40.0,
        verschmutzung=False,
        schmierung_ok=True,
        belueftet=True,
        welle_haerte_hrc=58.0,
    )
    base.update(over)
    return Fall(**base)


# --- saubere, vollständig bekannte Standardfälle → L2 (nicht überblocken) -------------------------
def test_clean_standard_cases_reach_L2():
    cases = {
        "Industriegetriebe Mineralöl 70C": _clean_known(
            drehzahl_rpm=1500, geschwindigkeit_ms=None
        ),
        "Pumpe Wasser 40C": _clean_known(
            medium="Wasser", medium_class="wasser", temperatur_c=40, welle_haerte_hrc=50
        ),
        "Diesel 50C": _clean_known(
            medium="Diesel", medium_class="diesel", temperatur_c=50, welle_haerte_hrc=55
        ),
        "Bremsflüssigkeit DOT4": _clean_known(
            medium="DOT4",
            medium_class="glykol_bremsfluessigkeit",
            temperatur_c=60,
            welle_haerte_hrc=50,
        ),
        "Silikonöl 80C": _clean_known(
            medium="Silikonöl",
            medium_class="silikonoel",
            temperatur_c=80,
            welle_haerte_hrc=50,
        ),
        "Heißwasser 95C": _clean_known(
            medium="Heißwasser",
            medium_class="wasser",
            temperatur_c=95,
            welle_haerte_hrc=50,
        ),
        "Vorbeugender Tausch": _clean_known(application_mode=AM.PREVENTIVE_REPLACEMENT),
    }
    for name, fall in cases.items():
        s = K(fall)
        assert s.response_level is RL.L2_SCREENING_CANDIDATE, (
            f"{name}: {s.response_level}"
        )


def test_material_candidate_sets_are_sane():
    assert (
        "EPDM" not in K(_clean_known(medium_class="mineraloel")).material_candidate_set
    )  # Öl → kein EPDM
    assert (
        "EPDM"
        in K(
            _clean_known(medium="Wasser", medium_class="wasser", welle_haerte_hrc=50)
        ).material_candidate_set
    )
    assert (
        "EPDM"
        in K(
            _clean_known(
                medium="Silikonöl", medium_class="silikonoel", welle_haerte_hrc=50
            )
        ).material_candidate_set
    )
    assert (
        "EPDM"
        not in K(
            _clean_known(medium="Diesel", medium_class="diesel", welle_haerte_hrc=55)
        ).material_candidate_set
    )
    # Bremsflüssigkeit: NBR/FKM ausgeschlossen
    bf = K(
        _clean_known(
            medium="DOT4", medium_class="glykol_bremsfluessigkeit", welle_haerte_hrc=50
        )
    ).material_candidate_set
    assert "NBR" not in bf and "FKM" not in bf


# --- riskante Fälle → deferieren (nicht L2) ------------------------------------------------------
def test_risky_cases_defer_to_L1():
    risky = {
        "Hochdrehzahl 12,6 m/s": _clean_known(
            drehzahl_rpm=12000,
            welle_d_mm=20,
            geschwindigkeit_ms=None,
            temperatur_c=90,
            welle_haerte_hrc=60,
        ),
        "Überdruck 0,3 bar": _clean_known(
            druck_bar=0.3,
            axiale_sicherung_ok=True,
            temperatur_c=80,
            welle_haerte_hrc=58,
        ),
        "Dampf 150C": _clean_known(
            medium="Dampf", medium_class="dampf", temperatur_c=150, welle_haerte_hrc=55
        ),
    }
    for name, fall in risky.items():
        assert K(fall).response_level is not RL.L2_SCREENING_CANDIDATE, name
    # Dampf: FKM ausgeschlossen
    assert (
        "FKM"
        not in K(
            _clean_known(
                medium="Dampf",
                medium_class="dampf",
                temperatur_c=150,
                welle_haerte_hrc=55,
            )
        ).material_candidate_set
    )


def test_freetext_and_incomplete_no_single_material():
    for fall in (
        Fall(
            medium="Hydrauliköl",
            medium_source=MS.FREE_TEXT,
            temperatur_c=80,
            druck_bar=0.0,
            geschwindigkeit_ms=2.0,
            verschmutzung=False,
            schmierung_ok=True,
            belueftet=True,
        ),
        Fall(
            medium="Öl",
            medium_source=MS.FREE_TEXT,
            welle_d_mm=50.0,
            geschwindigkeit_ms=3.0,
        ),
    ):
        s = K(fall)
        assert s.material_single is None
        assert s.response_level is not RL.L2_SCREENING_CANDIDATE


def test_leakage_is_failure_mode_first():
    for mode in (AM.LEAKAGE_FAILURE, AM.PREMATURE_FAILURE):
        s = K(_clean_known(application_mode=mode))
        assert (
            s.failure_mode_checklist
            and s.material_candidate_set == ()
            and s.din_candidate_label is None
        )


def test_critical_application_escalates_L0():
    assert (
        K(_clean_known(rohtext="Lebensmittelkontakt FDA")).response_level
        is RL.L0_ESCALATION
    )
    assert K(_clean_known(rohtext="ATEX-Bereich")).response_level is RL.L0_ESCALATION


# --- universelle harte Guards gelten auf ALLEN realen Fällen --------------------------------------
def test_hard_guards_hold_on_all_real_cases():
    alle = [
        _clean_known(),
        _clean_known(medium="Wasser", medium_class="wasser"),
        _clean_known(druck_bar=0.6),
        _clean_known(drehzahl_rpm=12000, welle_d_mm=20, geschwindigkeit_ms=None),
        _clean_known(application_mode=AM.LEAKAGE_FAILURE),
        _clean_known(rohtext="ATEX"),
        Fall(medium="Öl", medium_source=MS.FREE_TEXT, geschwindigkeit_ms=3.0),
        _clean_known(verschmutzung=True, welle_haerte_hrc=55),  # A2b
    ]
    for fall in alle:
        s = K(fall)
        assert s.final_design_code is None  # G3: nie ein finaler DIN-Code
        assert s.material_single is None  # G2: nie ein Einzelwerkstoff
        assert s.freigegeben is False  # G1: nie freigegeben
        assert s.response_level in (
            RL.L0_ESCALATION,
            RL.L1_CANDIDATE_SPACE,
            RL.L2_SCREENING_CANDIDATE,
        )  # max L2


def test_open_finding_A2b_is_documented_not_silently_wrong():
    # A2b: staubiger Standard-AS-Fall mit bekannter Härte. Engine derzeit L1 (Envelope: jede Verschmutzung
    # = nicht grün). OFFENE DOMÄNEN-KALIBRIERUNG für die Fachsignatur: soll Schmutz + AS + Härte≥55 grün/L2
    # sein (AS ist dafür gemacht)? Wir pinnen NICHT auf eine Meinung — wir prüfen nur die SICHEREN Eigenschaften.
    s = K(
        _clean_known(
            verschmutzung=True, welle_haerte_hrc=55, medium="Fett", medium_class="fett"
        )
    )
    assert s.response_level in (
        RL.L1_CANDIDATE_SPACE,
        RL.L2_SCREENING_CANDIDATE,
    )  # beide sicher
    assert (
        s.final_design_code is None
        and s.material_single is None
        and s.freigegeben is False
    )
