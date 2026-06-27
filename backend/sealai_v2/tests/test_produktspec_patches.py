"""Fachreview-Patches A6/A9/A10/B4/D2/A5/A8 als rote Schranken (Wissensaufbau-Loop: jede Experten-Antwort
→ Regel-ID → Test). Plus die strukturelle Verbesserung: nie 'bare empty', Werkstoff ist typisiert."""

from __future__ import annotations

from sealai_v2.knowledge.produktspec.contracts import (
    EnvelopeBand,
    Fall,
    MaterialKind,
    MediumSource as MS,
    ResponseLevel as RL,
)
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation as K


def _f(**o) -> Fall:
    base = dict(
        medium_source=MS.EXACT,
        druck_bar=0.0,
        geschwindigkeit_ms=3.0,
        welle_d_mm=40,
        verschmutzung=False,
        schmierung_ok=True,
        belueftet=True,
        welle_haerte_hrc=58,
    )
    base.update(o)
    return Fall(**base)


def test_patch1_steam_high_is_escalation_not_empty():  # A6
    s = K(
        _f(medium="Dampf", medium_class="dampf", temperatur_c=130, welle_haerte_hrc=50)
    )
    assert s.material.kind is MaterialKind.SPECIAL_ESCALATION
    assert s.material.escalation and "FKM" in s.material.excluded
    assert s.material.primary == () and s.response_level is RL.L1_CANDIDATE_SPACE


def test_patch2_hfc_lowtemp_nbr_candidate_else_defer():  # A9 (Code-Loch geschlossen)
    s = K(_f(medium="HFC", medium_class="hfc", temperatur_c=50, welle_haerte_hrc=55))
    assert s.material.kind is MaterialKind.CANDIDATE_SET and s.material.primary == (
        "NBR",
    )
    assert s.response_level is RL.L1_CANDIDATE_SPACE  # additivabhängig → nicht L2
    assert (
        K(_f(medium="HFC", medium_class="hfc", temperatur_c=70)).material.kind
        is MaterialKind.EMPTY_UNKNOWN
    )


def test_patch6_hfd_is_escalation_not_empty():  # A10
    s = K(_f(medium="HFD", medium_class="hfd", temperatur_c=60))
    assert (
        s.material.kind is MaterialKind.SPECIAL_ESCALATION
        and "NBR" in s.material.excluded
    )


def test_patch3_half_bar_is_red_conservative():  # B4
    assert (
        K(
            _f(
                medium="Öl",
                medium_class="mineraloel",
                temperatur_c=80,
                druck_bar=0.5,
                axiale_sicherung_ok=True,
            )
        ).envelope_band
        is EnvelopeBand.RED
    )
    assert (
        K(
            _f(
                medium="Öl",
                medium_class="mineraloel",
                temperatur_c=80,
                druck_bar=0.4,
                axiale_sicherung_ok=True,
            )
        ).envelope_band
        is EnvelopeBand.ORANGE
    )


def test_patch5_diesel_has_fkm_alternative():  # A8
    s = K(
        _f(medium="Diesel", medium_class="diesel", temperatur_c=60, welle_haerte_hrc=55)
    )
    assert s.material.primary == ("NBR",)
    assert "FKM" in s.material.alternatives and "HNBR" in s.material.alternatives


def test_patch4_dirty_with_hardness_is_L2_unknown_stays_L1():  # D2
    s = K(
        _f(
            medium="Fett",
            medium_class="fett",
            temperatur_c=60,
            geschwindigkeit_ms=4,
            verschmutzung=True,
            welle_haerte_hrc=55,
        )
    )
    assert s.response_level is RL.L2_SCREENING_CANDIDATE
    assert any(
        a.name == "lip" and a.value == "main+dust_lip" for a in s.axes
    )  # AS gewählt
    s2 = K(
        _f(
            medium="Fett",
            medium_class="fett",
            temperatur_c=60,
            geschwindigkeit_ms=4,
            verschmutzung=True,
            welle_haerte_hrc=None,
        )
    )
    assert s2.response_level is RL.L1_CANDIDATE_SPACE  # Härte unbekannt → Gate


def test_struct_primary_alternative_split():  # A1
    s = K(_f(medium="Öl", medium_class="mineraloel", temperatur_c=80))
    assert (
        s.material.primary == ("NBR",) and "HNBR" in s.material.alternatives
    )  # nicht gleichrangig


def test_struct_no_bare_empty_material_always_typed():
    for fall in (
        _f(medium="Dampf", medium_class="dampf", temperatur_c=130),
        _f(medium="HFD", medium_class="hfd", temperatur_c=60),
        Fall(medium="x", medium_source=MS.FREE_TEXT, geschwindigkeit_ms=3.0),
    ):
        assert K(fall).material.kind in tuple(
            MaterialKind
        )  # immer typisiert, nie 'bare empty'
