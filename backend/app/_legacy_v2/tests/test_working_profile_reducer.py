from app._legacy_v2.state import SealAIState, WorkingProfile, merge_working_profile
from app._legacy_v2.state.sealai_state import (
    CalcResults,
    WorkingProfile as PillarWorkingProfile,
    merge_pillar_working_profile,
)


def test_merge_working_profile_deep_merge_list_and_dict() -> None:
    left = WorkingProfile(
        medium="HLP46",
        safety_flags=["A", "B"],
        calc_results={"m2": {"ok": True}, "m3": {"score": 0.4}},
    )
    right = WorkingProfile(
        pressure_bar=120.0,
        safety_flags=["B", "C"],
        calc_results={"m3": {"score": 0.9}, "m4": {"ok": True}},
    )

    merged = merge_working_profile(left, right)

    assert merged.medium == "HLP46"
    assert merged.pressure_bar == 120.0
    assert sorted(merged.safety_flags) == ["A", "B", "C"]
    assert merged.calc_results["m2"] == {"ok": True}
    assert merged.calc_results["m3"] == {"score": 0.9}
    assert merged.calc_results["m4"] == {"ok": True}


def test_merge_working_profile_returns_empty_when_both_none() -> None:
    merged = merge_working_profile(None, None)
    assert isinstance(merged, WorkingProfile)
    assert merged.as_dict() == {}


def test_sealai_state_uses_working_profile_single_source_of_truth() -> None:
    state = SealAIState(working_profile=WorkingProfile(medium="Wasser", pressure_bar=16.0))
    assert state.working_profile.engineering_profile.medium == "Wasser"
    assert state.working_profile.engineering_profile.pressure_bar == 16.0


def test_state_pillar_integrity() -> None:
    material_branch = PillarWorkingProfile(
        material_choice={"material": "PTFE", "confidence": "high"},
    )
    mechanical_branch = PillarWorkingProfile(
        calc_results=CalcResults(v_surface_m_s=2.5, pv_value_mpa_m_s=1.8),
    )

    merged = merge_pillar_working_profile(material_branch, mechanical_branch)

    assert merged.material_choice == {"material": "PTFE", "confidence": "high"}
    assert merged.calc_results is not None
    assert merged.calc_results.v_surface_m_s == 2.5
    assert merged.calc_results.pv_value_mpa_m_s == 1.8
