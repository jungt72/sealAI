from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text


def test_pressure_from_to_takes_target_value() -> None:
    params = extract_parameters_from_text("Der Druck ging von 10 auf 7.")
    assert params.get("pressure_bar") == 7.0


def test_pressure_from_to_with_bar_takes_target_value() -> None:
    params = extract_parameters_from_text("Druck von 10 bar auf 7 bar.")
    assert params.get("pressure_bar") == 7.0


def test_pressure_explicit_bar() -> None:
    params = extract_parameters_from_text("Betriebsdruck 7 bar.")
    assert params.get("pressure_bar") == 7.0


def test_standard_number_is_not_speed() -> None:
    params = extract_parameters_from_text("Bitte mit Quellen zu DIN 3761.")
    assert "speed_rpm" not in params
    assert "pressure_bar" not in params


def test_speed_requires_unit_or_context() -> None:
    params = extract_parameters_from_text("3761")
    assert "speed_rpm" not in params

    params2 = extract_parameters_from_text("Drehzahl 3761")
    assert params2.get("speed_rpm") == 3761.0

    params3 = extract_parameters_from_text("3761 rpm")
    assert params3.get("speed_rpm") == 3761.0
