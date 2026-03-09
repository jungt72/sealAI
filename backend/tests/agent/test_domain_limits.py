import pytest
from app.agent.domain.limits import OperatingLimit
from app.agent.domain.parameters import PhysicalParameter

def test_limit_celsius_in_range():
    """Test: Wert liegt innerhalb der Temperatur-Grenzen (Celsius)."""
    limit = OperatingLimit(min_value=-20.0, max_value=200.0, unit="C")
    
    # Innerhalb
    assert limit.is_within_limits(PhysicalParameter(value=100.0, unit="C")) is True
    # Am Rand
    assert limit.is_within_limits(PhysicalParameter(value=200.0, unit="C")) is True
    assert limit.is_within_limits(PhysicalParameter(value=-20.0, unit="C")) is True
    # Außerhalb
    assert limit.is_within_limits(PhysicalParameter(value=201.0, unit="C")) is False
    assert limit.is_within_limits(PhysicalParameter(value=-21.0, unit="C")) is False

def test_limit_fahrenheit_vs_celsius():
    """Test: Fahrenheit-Input gegen Celsius-Limit."""
    # Limit: 0°C bis 100°C
    limit = OperatingLimit(min_value=0.0, max_value=100.0, unit="C")
    
    # 32°F = 0°C (OK)
    assert limit.is_within_limits(PhysicalParameter(value=32.0, unit="F")) is True
    # 212°F = 100°C (OK)
    assert limit.is_within_limits(PhysicalParameter(value=212.0, unit="F")) is True
    # 213°F > 100°C (Nicht OK)
    assert limit.is_within_limits(PhysicalParameter(value=213.0, unit="F")) is False
    # 31°F < 0°C (Nicht OK)
    assert limit.is_within_limits(PhysicalParameter(value=31.0, unit="F")) is False

def test_limit_psi_vs_bar():
    """Test: PSI-Input gegen bar-Limit."""
    # Limit: 0 bis 10 bar
    limit = OperatingLimit(min_value=0.0, max_value=10.0, unit="bar")
    
    # 100 psi ≈ 6.89 bar (OK)
    assert limit.is_within_limits(PhysicalParameter(value=100.0, unit="psi")) is True
    # 150 psi ≈ 10.34 bar (Nicht OK)
    assert limit.is_within_limits(PhysicalParameter(value=150.0, unit="psi")) is False

def test_limit_no_lower_bound():
    """Test: Grenze ohne Untergrenze."""
    limit = OperatingLimit(max_value=50.0, unit="bar")
    
    assert limit.is_within_limits(PhysicalParameter(value=-100.0, unit="bar")) is True
    assert limit.is_within_limits(PhysicalParameter(value=50.0, unit="bar")) is True
    assert limit.is_within_limits(PhysicalParameter(value=51.0, unit="bar")) is False

def test_limit_no_upper_bound():
    """Test: Grenze ohne Obergrenze."""
    limit = OperatingLimit(min_value=10.0, unit="C")
    
    assert limit.is_within_limits(PhysicalParameter(value=1000.0, unit="C")) is True
    assert limit.is_within_limits(PhysicalParameter(value=10.0, unit="C")) is True
    assert limit.is_within_limits(PhysicalParameter(value=9.0, unit="C")) is False
