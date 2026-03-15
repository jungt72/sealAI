import pytest
from app.agent.case_state import _infer_unit, _normalize_snapshot_value

@pytest.mark.parametrize("key,expected", [
    ("pressure", "bar"),
    ("pressure_bar", "bar"),
    ("temperature", "C"),
    ("temperature_c", "C"),
    ("temperature_f", "F"),
    ("diameter", "mm"),
    ("shaft_diameter_mm", "mm"),
    ("speed", "rpm"),
    ("max_speed_rpm", "rpm"),
    ("unknown", None),
])
def test_infer_unit(key, expected):
    assert _infer_unit(key) == expected

@pytest.mark.parametrize("key,value,expected", [
    ("material", "Viton", "FKM"),
    ("medium", "Wasser", "Wasser"),
    ("medium", "water", "Wasser"),
    ("temperature_f", 68.0, 20.0), # 68F -> 20C
    ("pressure_psi", 145.0, 9.997402), # 145 psi -> ~10 bar
    ("unknown", "value", "value"),
])
def test_normalize_snapshot_value(key, value, expected):
    result = _normalize_snapshot_value(value, key)
    if isinstance(expected, float):
        assert result == pytest.approx(expected, abs=0.1)
    else:
        assert result == expected
