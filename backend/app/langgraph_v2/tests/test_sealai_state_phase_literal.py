from typing import get_args

from app.langgraph_v2.phase import PHASE_VALUES
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.types import PhaseLiteral


def test_sealai_state_accepts_all_phase_values() -> None:
    for phase in PHASE_VALUES:
        state = SealAIState(phase=phase)
        assert state.phase == phase


def test_phase_literal_matches_phase_constants() -> None:
    assert set(PHASE_VALUES) == set(get_args(PhaseLiteral))
