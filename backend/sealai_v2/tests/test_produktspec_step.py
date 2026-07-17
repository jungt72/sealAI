"""Tests for the pipeline-layer Produktspec adapter (case-state → Fall → render dict).

The produktspec kernel itself is covered by test_produktspec*.py (38 tests); these cover only the
adapter glue: number parsing, the case→Fall mapping, and the flag/RWDR/basis gating + fail-open."""

from __future__ import annotations

from sealai_v2.core.contracts import RememberedFact
from sealai_v2.knowledge.produktspec.contracts import MediumSource
from sealai_v2.pipeline.produktspec_step import (
    _num,
    case_state_to_fall,
    compute_kandidaten_spec,
    not_available_for_seal_type_marker,
)


def _facts(**kv):
    return tuple(
        RememberedFact(feld=k, wert=v, provenance="user-form") for k, v in kv.items()
    )


def test_num_parses_units_and_german_comma():
    assert _num("40 mm") == 40.0
    assert _num("0,5 bar") == 0.5
    assert _num("-10 °C") == -10.0
    assert _num("5000 U/min") == 5000.0
    assert _num("") is None
    assert _num("Unbekannt") is None


def test_case_state_to_fall_maps_clean_fields_and_keeps_free_text_medium():
    fall = case_state_to_fall(
        _facts(
            medium="Hydrauliköl",
            betriebstemperatur="90 °C",
            druck="0,5 bar",
            drehzahl="5000 U/min",
            wellendurchmesser="40 mm",
            haerte="45 HRC",
            drall="drallfrei",
            verschmutzung="stark",
        ),
        question="RWDR für eine Pumpe",
    )
    assert fall.medium == "Hydrauliköl"
    assert (
        fall.medium_source is MediumSource.FREE_TEXT
    )  # G2: never promotes a single material
    assert fall.temperatur_c == 90.0
    assert fall.druck_bar == 0.5
    assert fall.drehzahl_rpm == 5000.0
    assert fall.welle_d_mm == 40.0
    assert fall.welle_haerte_hrc == 45.0
    assert fall.welle_drall is False
    assert fall.verschmutzung is True
    assert fall.rohtext == "RWDR für eine Pumpe"


def test_compute_gated_off_returns_none():
    assert (
        compute_kandidaten_spec(
            _facts(medium="Öl"), "q", enabled=False, seal_type="rwdr"
        )
        is None
    )


def test_compute_non_rwdr_seal_type_returns_structured_marker_not_none():
    # OD-3: a non-RWDR seal type is a structural scope boundary, not a silent None -- the caller
    # (and ultimately the frontend render surface) can tell "out of scope for this seal type"
    # apart from "nothing to specify yet" (which still returns plain None, see the no-basis test).
    spec = compute_kandidaten_spec(
        _facts(medium="Öl"), "q", enabled=True, seal_type="hydraulik"
    )
    assert spec == {
        "status": "not_available_for_seal_type",
        "seal_type": "hydraulik",
        "geltungsrahmen": (
            'Kandidaten-Spezifikation ist für den Dichtungstyp "hydraulik" nicht '
            "verfügbar — die Regel-Engine deckt ausschließlich RWDR/DIN-3760 ab."
        ),
    }


def test_compute_glrd_returns_structured_marker():
    # OD-3 worked example 1/2: Gleitringdichtung (GLRD) -- a real, non-RWDR seal type extracted by
    # core.seal_type_extract -- gets the marker even with a full engineering basis (medium +
    # Wellendurchmesser), not the RWDR candidate dict.
    spec = compute_kandidaten_spec(
        _facts(
            medium="Mineralöl",
            wellendurchmesser="40 mm",
            drehzahl="3000 U/min",
            betriebstemperatur="80 °C",
        ),
        "GLRD für ein Getriebe",
        enabled=True,
        seal_type="Gleitringdichtung",
    )
    assert spec["status"] == "not_available_for_seal_type"
    assert spec["seal_type"] == "Gleitringdichtung"
    assert "material" not in spec  # never the RWDR shape's rich keys
    assert "axes" not in spec


def test_compute_o_ring_returns_structured_marker():
    # OD-3 worked example 2/2: O-Ring, same basis as the RWDR-success test below.
    spec = compute_kandidaten_spec(
        _facts(
            medium="Mineralöl",
            wellendurchmesser="40 mm",
            drehzahl="3000 U/min",
            betriebstemperatur="80 °C",
        ),
        "O-Ring für eine Pumpe",
        enabled=True,
        seal_type="O-Ring",
    )
    assert spec == not_available_for_seal_type_marker("O-Ring")


def test_compute_skips_when_no_basis_even_for_non_rwdr():
    # The no-basis short-circuit only applies to the RWDR path; a non-RWDR seal type returns the
    # marker regardless of basis (it is a scope statement, not a data-completeness statement).
    spec = compute_kandidaten_spec(
        _facts(), "q", enabled=True, seal_type="O-Ring"
    )
    assert spec["status"] == "not_available_for_seal_type"


def test_compute_skips_when_no_basis():
    assert (
        compute_kandidaten_spec(
            _facts(betriebstemperatur="90 °C"), "q", enabled=True, seal_type="rwdr"
        )
        is None
    )


def test_compute_rwdr_with_basis_returns_structurally_capped_candidate_dict():
    spec = compute_kandidaten_spec(
        _facts(
            medium="Mineralöl",
            wellendurchmesser="40 mm",
            drehzahl="3000 U/min",
            betriebstemperatur="80 °C",
        ),
        "RWDR für ein Getriebe",
        enabled=True,
        seal_type="rwdr",  # an empty seal_type (RWDR default) also computes — covered by the call below
    )
    assert spec is not None
    # structural invariants ride along (G1 freigegeben False, G3 no final code)
    assert spec["freigegeben"] is False
    assert spec["final_design_code"] is None
    assert spec["response_level"] in (
        "L0_escalation",
        "L1_candidate_space",
        "L2_screening_candidate",
    )
    assert spec["geltungsrahmen"]  # the Geltungsrahmen framing is always present
    assert isinstance(spec["axes"], list)
    assert "material_candidate_set" in spec


def test_compute_empty_seal_type_defaults_to_rwdr():
    spec = compute_kandidaten_spec(
        _facts(wellendurchmesser="50 mm"), "q", enabled=True, seal_type=""
    )
    assert spec is not None
