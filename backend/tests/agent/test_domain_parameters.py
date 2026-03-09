import pytest
from pydantic import ValidationError
from app.agent.domain.parameters import PhysicalParameter

def test_parameter_instantiation_valid():
    """Test: Erfolgreiche Instanziierung mit gültigen Werten."""
    p = PhysicalParameter(value=10.0, unit="bar")
    assert p.value == 10.0
    assert p.unit == "bar"

def test_conversion_psi_to_bar():
    """Test: Korrekte Umrechnung von psi nach bar."""
    # 100 psi * 0.0689476 = 6.89476 bar
    p = PhysicalParameter(value=100.0, unit="psi")
    assert p.to_base_unit() == pytest.approx(6.89476)
    assert p.base_unit == "bar"

def test_conversion_f_to_c():
    """Test: Korrekte Umrechnung von Fahrenheit nach Celsius."""
    # (212°F - 32) * 5/9 = 100°C
    p = PhysicalParameter(value=212.0, unit="F")
    assert p.to_base_unit() == pytest.approx(100.0)
    assert p.base_unit == "C"

def test_conversion_c_to_c():
    """Test: Celsius bleibt Celsius."""
    p = PhysicalParameter(value=25.0, unit="C")
    assert p.to_base_unit() == 25.0
    assert p.base_unit == "C"

def test_invalid_unit():
    """Test: Pydantic lehnt ungültige Einheiten ab."""
    with pytest.raises(ValidationError):
        PhysicalParameter(value=10.0, unit="kg")

def test_extra_fields():
    """Test: Pydantic lehnt extra Felder ab."""
    with pytest.raises(ValidationError):
        PhysicalParameter(value=10.0, unit="bar", extra="unsupported")
