import pytest

from app.langgraph_v2.state import TechnicalParameters


def test_pressure_bar_accepts_number() -> None:
    params = TechnicalParameters(pressure_bar=10)
    assert params.pressure_bar == 10


def test_pressure_bar_parses_string_with_unit() -> None:
    params = TechnicalParameters(pressure_bar="10 bar")
    assert params.pressure_bar == 10


def test_pressure_bar_rejects_non_numeric_string() -> None:
    with pytest.raises(ValueError, match="pressure_bar must be a number"):
        TechnicalParameters(pressure_bar="bar")
