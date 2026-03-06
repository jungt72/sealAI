from typing import get_args

from app.langgraph_v2.phase import PHASE_VALUES
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.state.sealai_state import merge_dicts, take_last_non_null
from app.langgraph_v2.types import PhaseLiteral


def test_sealai_state_accepts_all_phase_values() -> None:
    for phase in PHASE_VALUES:
        state = SealAIState(phase=phase)
        assert state.reasoning.phase == phase


def test_phase_literal_matches_phase_constants() -> None:
    assert set(PHASE_VALUES) == set(get_args(PhaseLiteral))


def test_take_last_non_null_prefers_latest_non_null() -> None:
    assert take_last_non_null("routing", "confirm") == "confirm"
    assert take_last_non_null("routing", None) == "routing"
    assert take_last_non_null(None, "confirm") == "confirm"


def test_merge_dicts_deep_merges_nested_values() -> None:
    left = {"a": 1, "nested": {"x": 1, "keep": True}}
    right = {"b": 2, "nested": {"x": 3}}
    merged = merge_dicts(left, right)
    assert merged == {"a": 1, "b": 2, "nested": {"x": 3, "keep": True}}
