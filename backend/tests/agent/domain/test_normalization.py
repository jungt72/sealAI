import pytest

from app.agent.domain.normalization import (
    extract_parameters,
    normalize_material,
    normalize_material_decision,
    normalize_medium,
    normalize_medium_decision,
    normalize_medium_id,
    normalize_unit_value,
)


@pytest.mark.parametrize("input_name,expected", [("Viton", "FKM"), ("Kalrez", "FFKM"), ("Teflon", "PTFE"), ("nitril", "NBR"), ("Unknown", "Unknown"), (None, None)])
def test_normalize_material(input_name, expected):
    assert normalize_material(input_name) == expected


@pytest.mark.parametrize("input_name,expected", [("Wasser", "Wasser"), ("oil", "Öl"), ("Panolin", "Bio-Öl"), ("Unknown", "Unknown"), (None, None)])
def test_normalize_medium(input_name, expected):
    assert normalize_medium(input_name) == expected


def test_normalize_medium_id_conservative_passthrough():
    assert normalize_medium_id("Öliges Medium") == "Öliges Medium"


def test_normalize_unit_value():
    value, unit = normalize_unit_value(68, "F")
    assert value == pytest.approx(20, abs=0.1)
    assert unit == "C"


def test_extract_parameters_marks_trade_name_mappings_as_confirmation_required():
    extracted = extract_parameters("Medium ist Panolin und das Material ist Viton. 77°F und 145 psi")
    assert extracted["medium_confirmation_required"] == "Bio-Öl"
    assert extracted["material_confirmation_required"] == "FKM"
    assert extracted["temperature_c"] == pytest.approx(25, abs=1)
    assert extracted["pressure_bar"] == pytest.approx(10, abs=1)


def test_normalization_decisions_distinguish_confirmation_and_inference():
    assert normalize_material_decision("Viton").status == "confirmation_required"
    assert normalize_material_decision("nitril").status == "inferred"
    assert normalize_medium_decision("Panolin").status == "confirmation_required"
