"""Produktspec v3.1 — die ROTEN SCHRANKEN (Konzept v3.1). Beweist: sicher deferieren, nichts fabrizieren,
saubere Standardfälle als L2 durchlassen (False-Negative-Kontrolle), Freitext nie → Einzelwerkstoff,
nie finaler DIN-Code, max L2, Constraint-/Defer-Verhalten, Leckage = Failure-Mode-first."""

from __future__ import annotations

from sealai_v2.knowledge.produktspec.contracts import (
    VERBOTENE_WOERTER,
    ApplicationMode,
    EnvelopeBand,
    Fall,
    Kritikalitaet,
    MediumSource,
    ResponseLevel,
)
from sealai_v2.knowledge.produktspec.kernel import render_texts
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation as K


def _clean(**over) -> Fall:
    base = dict(
        medium="Mineralöl",
        medium_class="mineraloel",
        medium_source=MediumSource.EXACT,
        temperatur_c=90.0,
        druck_bar=0.0,
        geschwindigkeit_ms=11.0,
        welle_d_mm=50.0,
        verschmutzung=False,
        schmierung_ok=True,
        belueftet=True,
        application_mode=ApplicationMode.NEW,
    )
    base.update(over)
    return Fall(**base)


# --- False-Negative-Kontrolle: der aufgelöste Widerspruch ----------------------------------------
def test_clean_standard_case_11ms_is_L2_with_checkpoint():
    s = K(_clean())  # belüftet, sauberes Mineralöl exakt, 90°C, 11 m/s
    assert s.envelope_band is EnvelopeBand.GREEN_EXTENDED
    assert (
        s.response_level is ResponseLevel.L2_SCREENING_CANDIDATE
    )  # NICHT vorschnell Defer
    assert s.din_candidate_label and "Kandidatenraum" in s.din_candidate_label
    assert s.open_verifications  # mit Prüfpunkt (Welle/Gehäuse)
    assert "NBR" in s.material_candidate_set
    assert s.freigegeben is False


def test_eight_ms_clean_is_green_base_L2():
    s = K(_clean(geschwindigkeit_ms=7.0, temperatur_c=70.0))
    assert s.envelope_band is EnvelopeBand.GREEN_BASE
    assert s.response_level is ResponseLevel.L2_SCREENING_CANDIDATE


def test_thirteen_ms_is_orange_L1():
    s = K(_clean(geschwindigkeit_ms=13.0))
    assert s.envelope_band is EnvelopeBand.ORANGE
    assert s.response_level is ResponseLevel.L1_CANDIDATE_SPACE
    assert s.din_candidate_label is None


def test_pressure_over_02bar_orange_L1():
    s = K(_clean(druck_bar=0.4, axiale_sicherung_ok=True))
    assert (
        s.envelope_band is EnvelopeBand.ORANGE
        and s.response_level is ResponseLevel.L1_CANDIDATE_SPACE
    )


def test_red_pressure_outside_scope():
    s = K(_clean(druck_bar=0.6))
    assert s.envelope_band is EnvelopeBand.RED
    assert (
        s.response_level is ResponseLevel.L1_CANDIDATE_SPACE
        and s.din_candidate_label is None
    )


# --- G2: Freitext nie → Einzelwerkstoff; max L1 ---------------------------------------------------
def test_free_text_medium_never_single_material_max_L1():
    s = K(
        Fall(
            medium="Öl",
            medium_class="",
            medium_source=MediumSource.FREE_TEXT,
            temperatur_c=90.0,
            druck_bar=0.0,
            geschwindigkeit_ms=8.0,
            verschmutzung=False,
            schmierung_ok=True,
            belueftet=True,
        )
    )
    assert s.material_single is None
    assert (
        s.response_level is not ResponseLevel.L2_SCREENING_CANDIDATE
    )  # Freitext → kein L2


# --- G3: nie ein finaler DIN-Code; max L2 ---------------------------------------------------------
def test_never_final_din_code_and_max_L2():
    for fall in (_clean(), _clean(druck_bar=0.6), _clean(geschwindigkeit_ms=13.0)):
        s = K(fall)
        assert s.final_design_code is None
        assert s.material_single is None
        assert s.response_level in (
            ResponseLevel.L0_ESCALATION,
            ResponseLevel.L1_CANDIDATE_SPACE,
            ResponseLevel.L2_SCREENING_CANDIDATE,
        )


# --- Werkstofflogik ------------------------------------------------------------------------------
def test_epdm_excluded_for_mineral_oil():
    s = K(_clean(temperatur_c=80.0))
    assert "EPDM" not in s.material_candidate_set
    assert "NBR" in s.material_candidate_set


def test_silicone_oil_not_excluded_by_oil_keyword():
    s = K(_clean(medium="Silikonöl", medium_class="silikonoel"))
    assert "EPDM" in s.material_candidate_set  # silicone is NOT a hydrocarbon


def test_aggressive_unclassified_no_elastomer_candidate():
    s = K(
        Fall(
            medium="aggressive Chemie",
            medium_source=MediumSource.FREE_TEXT,
            temperatur_c=60.0,
            druck_bar=0.0,
            verschmutzung=False,
        )
    )
    assert s.material_candidate_set == ()
    assert any("aggressive" in d.lower() or "sds" in d.lower() for d in s.defer_gruende)


# --- Anwendungsmodi ------------------------------------------------------------------------------
def test_leakage_is_failure_mode_first():
    s = K(_clean(application_mode=ApplicationMode.LEAKAGE_FAILURE))
    assert s.failure_mode_checklist and s.material_candidate_set == ()
    assert s.din_candidate_label is None


def test_preventive_replacement_allows_L2_screening():
    s = K(_clean(application_mode=ApplicationMode.PREVENTIVE_REPLACEMENT))
    assert (
        s.response_level is ResponseLevel.L2_SCREENING_CANDIDATE
    )  # not blocked like leakage


# --- Welle-Gates + Drall + Kritikalität ----------------------------------------------------------
def test_shaft_lead_gate_blocks():
    s = K(_clean(welle_drall=True))
    assert s.response_level is ResponseLevel.L1_CANDIDATE_SPACE
    assert any("drall" in d.lower() for d in s.defer_gruende)


def test_hardness_unknown_is_open_verification_in_clean_case():
    s = K(_clean())  # v=11, hardness unknown, clean → open_verification, NICHT Gate
    assert s.response_level is ResponseLevel.L2_SCREENING_CANDIDATE
    assert any("härte" in o.lower() for o in s.open_verifications)


def test_criticality_atex_L0():
    s = K(_clean(rohtext="Einsatz im ATEX-Bereich"))
    assert s.kritikalitaet is Kritikalitaet.HIGH_RISK
    assert s.response_level is ResponseLevel.L0_ESCALATION


# --- Sprache + Provenance ------------------------------------------------------------------------
def test_no_forbidden_words():
    for fall in (
        _clean(),
        _clean(druck_bar=0.6),
        _clean(application_mode=ApplicationMode.LEAKAGE_FAILURE),
    ):
        text = render_texts(K(fall))
        for w in VERBOTENE_WOERTER:
            assert w not in text, f"verbotenes Wort '{w}'"


def test_provenance_present_on_L2():
    s = K(_clean())
    assert s.quellen  # rule provenance per axis
