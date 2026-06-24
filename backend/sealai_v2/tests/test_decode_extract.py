"""decode_designation — deterministic seal-designation parser (Modus G). Offline, no LLM."""

from __future__ import annotations

from sealai_v2.core.decode_extract import decode_designation


def test_rwdr_three_dims_id_od_width():
    r = decode_designation("RWDR 40x62x10 FKM")
    assert r["type"] == "RWDR"
    assert r["material"] == "FKM"
    assert (r["id_mm"], r["od_mm"], r["width_mm"]) == (40.0, 62.0, 10.0)
    assert r["dim_interpretation"] == "id_od_breite"


def test_dash_separator_and_decimal():
    r = decode_designation("Wellendichtring 40-62-10 NBR")
    assert r["type"] == "Wellendichtring"
    assert r["id_mm"] == 40.0 and r["width_mm"] == 10.0


def test_oring_two_dims_id_cord():
    r = decode_designation("O-Ring 40x3 EPDM")
    assert r["type"] == "O-Ring"
    assert r["id_mm"] == 40.0 and r["cord_mm"] == 3.0
    assert r["dim_interpretation"] == "id_schnurstaerke"


def test_ambiguous_two_dims_not_mislabelled():
    # two numbers, no O-Ring type → do not guess id/od vs id/cord
    r = decode_designation("Dichtung 40x62 NBR")
    assert r["dim_interpretation"] == "uneindeutig"
    assert "id_mm" not in r  # conservative: no labelled id/od


def test_material_only_still_decodes():
    r = decode_designation("eine FKM-Dichtung")
    assert r is not None and r["material"] == "FKM"
    assert "dims_mm" not in r


def test_nothing_decodable_is_none():
    assert decode_designation("Welche Dichtung empfehlen Sie?") is None


def test_dims_are_result_side_not_narration():
    # the parsed dims live in the structured result; the parser never produces prose
    r = decode_designation("BAUMSL 40-62-10 FKM")
    assert isinstance(r["dims_mm"], list) and r["dims_mm"] == [40.0, 62.0, 10.0]
