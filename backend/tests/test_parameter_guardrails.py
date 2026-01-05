from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_lww


def test_pressure_operating_cannot_exceed_max() -> None:
    merged, _prov, versions, updated_at, applied, rejected = apply_parameter_patch_lww(
        existing={"pressure_bar": 2, "pressure_max": 4},
        patch={"pressure_bar": 5},
        provenance={"pressure_bar": "user"},
        source="user",
        parameter_versions={"pressure_bar": 1, "pressure_max": 1},
        parameter_updated_at={"pressure_bar": 100.0, "pressure_max": 100.0},
        base_versions={"pressure_bar": 1},
        now=lambda: 200.0,
    )

    assert merged["pressure_bar"] == 2
    assert applied == []
    assert rejected == [
        {
            "field": "pressure_bar",
            "reason": "pressure_range_invalid",
            "details": {"rule": "op<=max", "op": 5.0, "max": 4.0},
        }
    ]
    assert versions["pressure_bar"] == 1
    assert updated_at["pressure_bar"] == 100.0


def test_pressure_min_cannot_exceed_max() -> None:
    merged, _prov, versions, updated_at, applied, rejected = apply_parameter_patch_lww(
        existing={},
        patch={"pressure_min": 5, "pressure_max": 1},
        provenance={},
        source="user",
        parameter_versions={},
        parameter_updated_at={},
        base_versions={"pressure_min": 0, "pressure_max": 0},
        now=lambda: 50.0,
    )

    assert "pressure_min" not in merged
    assert "pressure_max" not in merged
    assert applied == []
    assert rejected == [
        {
            "field": "pressure_min",
            "reason": "pressure_range_invalid",
            "details": {"rule": "min<=max", "min": 5.0, "max": 1.0},
        },
        {
            "field": "pressure_max",
            "reason": "pressure_range_invalid",
            "details": {"rule": "min<=max", "min": 5.0, "max": 1.0},
        },
    ]
    assert versions.get("pressure_min", 0) == 0
    assert versions.get("pressure_max", 0) == 0
    assert updated_at == {}


def test_temp_operating_within_range() -> None:
    merged, _prov, versions, updated_at, applied, rejected = apply_parameter_patch_lww(
        existing={"temp_min": 0, "temp_max": 100},
        patch={"temperature_C": 50},
        provenance={},
        source="user",
        parameter_versions={"temperature_C": 0},
        parameter_updated_at={"temperature_C": 10.0},
        base_versions={"temperature_C": 0},
        now=lambda: 20.0,
    )

    assert merged["temperature_C"] == 50
    assert applied == ["temperature_C"]
    assert rejected == []
    assert versions["temperature_C"] == 1
    assert updated_at["temperature_C"] == 20.0
