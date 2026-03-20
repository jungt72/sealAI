import pytest

from app.agent.case_state import _infer_unit, _normalize_snapshot_value


@pytest.mark.parametrize("key,expected", [("pressure", "bar"), ("temperature_f", "F"), ("speed", "rpm"), ("unknown", None)])
def test_infer_unit(key, expected):
    assert _infer_unit(key) == expected


@pytest.mark.parametrize("key,value,expected", [("material", "Viton", "Viton"), ("material", "Nitril", "NBR"), ("medium", "water", "Wasser"), ("temperature_f", 68.0, 20.0), ("pressure_psi", 145.0, 9.997402)])
def test_normalize_snapshot_value(key, value, expected):
    result = _normalize_snapshot_value(value, key)
    if isinstance(expected, float):
        assert result == pytest.approx(expected, abs=0.1)
    else:
        assert result == expected
