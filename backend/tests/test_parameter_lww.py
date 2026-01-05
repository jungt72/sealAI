from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_lww


def test_parameter_patch_rejects_stale_base_version() -> None:
    merged, _prov, versions, updated_at, applied, rejected = apply_parameter_patch_lww(
        existing={"pressure_bar": 5},
        patch={"pressure_bar": 7},
        provenance={"pressure_bar": "user"},
        source="user",
        parameter_versions={"pressure_bar": 2},
        parameter_updated_at={"pressure_bar": 100.0},
        base_versions={"pressure_bar": 1},
        now=lambda: 200.0,
    )

    assert merged["pressure_bar"] == 5
    assert applied == []
    assert rejected == [{"field": "pressure_bar", "reason": "stale"}]
    assert versions["pressure_bar"] == 2
    assert updated_at["pressure_bar"] == 100.0


def test_parameter_patch_applies_and_increments_version() -> None:
    merged, _prov, versions, updated_at, applied, rejected = apply_parameter_patch_lww(
        existing={"medium": "water"},
        patch={"medium": "oil"},
        provenance={"medium": "user"},
        source="user",
        parameter_versions={"medium": 1},
        parameter_updated_at={"medium": 123.0},
        base_versions={"medium": 1},
        now=lambda: 456.0,
    )

    assert merged["medium"] == "oil"
    assert applied == ["medium"]
    assert rejected == []
    assert versions["medium"] == 2
    assert updated_at["medium"] == 456.0
