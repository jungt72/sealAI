from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text


def test_extract_pressure_bar_with_unit() -> None:
    params = extract_parameters_from_text("Bitte ändere den Betriebsdruck auf 7 bar.")
    assert params.get("pressure_bar") == 7


def test_extract_pressure_bar_from_druck_phrase() -> None:
    params = extract_parameters_from_text("Der Druck ging von 10 auf 7.")
    assert params.get("pressure_bar") == 7
