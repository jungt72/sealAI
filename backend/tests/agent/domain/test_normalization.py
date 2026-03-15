import pytest
from app.agent.domain.normalization import normalize_material, normalize_medium, normalize_medium_id, normalize_unit_value, extract_parameters

@pytest.mark.parametrize("input_name,expected", [
    ("Viton", "FKM"),
    ("viton", "FKM"),
    ("Kalrez", "FFKM"),
    ("Teflon", "PTFE"),
    ("NBR", "NBR"),
    ("nitril", "NBR"),
    ("Unknown", "Unknown"),
    (None, None),
])
def test_normalize_material(input_name, expected):
    assert normalize_material(input_name) == expected

@pytest.mark.parametrize("input_name,expected", [
    ("Wasser", "Wasser"),
    ("water", "Wasser"),
    ("Öl", "Öl"),
    ("oil", "Öl"),
    ("Mineralöl", "Öl"),
    ("Bio-Öl", "Bio-Öl"),
    ("Panolin", "Bio-Öl"),
    ("Ester", "Bio-Öl"),
    ("HEES", "Bio-Öl"),
    ("HLP", "Öl"),
    ("Unknown", "Unknown"),
    (None, None),
])
def test_normalize_medium(input_name, expected):
    assert normalize_medium(input_name) == expected

@pytest.mark.parametrize("input_name,expected", [
    # HEES / Bio-Öl family
    ("Bio-Öl", "hees"),
    ("Panolin", "hees"),
    ("Ester", "hees"),
    ("HEES", "hees"),
    ("hees", "hees"),
    # HLP / mineral oil family
    ("Öl", "hlp"),
    ("oil", "hlp"),
    ("Mineralöl", "hlp"),
    ("Hydrauliköl", "hlp"),
    ("HLP", "hlp"),
    ("hlp", "hlp"),
    # Water
    ("Wasser", "wasser"),
    ("water", "wasser"),
    # Conservative: unknown inputs pass through unchanged
    ("None", "None"),
    (None, None),
])
def test_normalize_medium_id(input_name, expected):
    assert normalize_medium_id(input_name) == expected


@pytest.mark.parametrize("input_name,expected", [
    # Conservative pass-through: ambiguous free-text must not collapse to an ID
    ("Öliges Medium", "Öliges Medium"),
    ("Wasserbasiert", "Wasserbasiert"),
    ("Kühlschmierstoff", "Kühlschmierstoff"),
    ("synth. Öl-Wasser-Emulsion", "synth. Öl-Wasser-Emulsion"),
])
def test_normalize_medium_id_conservative_passthrough(input_name, expected):
    """Ambiguous or compound strings must not be force-mapped to a technical ID."""
    assert normalize_medium_id(input_name) == expected


def test_normalize_medium_conservative():
    # Test that partial strings don't over-normalize if not whole words
    assert normalize_medium("Öliges Medium") == "Öliges Medium"
    assert normalize_medium("Wasserbasiert") == "Wasserbasiert"
    assert normalize_medium("Bio-Öl") == "Bio-Öl"

@pytest.mark.parametrize("val,unit,expected_val,expected_unit", [
    (100, "bar", 100, "bar"),
    (14.5038, "psi", 1.0, "bar"),
    (20, "C", 20, "C"),
    (68, "F", 20, "C"),
])
def test_normalize_unit_value(val, unit, expected_val, expected_unit):
    norm_val, norm_unit = normalize_unit_value(val, unit)
    assert norm_val == pytest.approx(expected_val, abs=0.1)
    assert norm_unit == expected_unit

def test_extract_parameters():
    text = "Die Temperatur liegt bei 100°C und der Druck bei 50 bar. Medium ist Viton-verträgliches Öl."
    extracted = extract_parameters(text)
    
    assert extracted["temperature_c"] == 100
    assert extracted["pressure_bar"] == 50
    assert extracted["medium_normalized"] == "Öl"
    assert extracted["material_normalized"] == "FKM"

def test_extract_parameters_psi_f():
    text = "77°F and 145 psi"
    extracted = extract_parameters(text)
    
    assert extracted["temperature_c"] == pytest.approx(25, abs=1)
    assert extracted["pressure_bar"] == pytest.approx(10, abs=1)

def test_extract_parameters_speed_diam():
    text = "Welle 50mm, Drehzahl 3000 rpm"
    extracted = extract_parameters(text)
    
    assert extracted["diameter_mm"] == 50
    assert extracted["speed_rpm"] == 3000
