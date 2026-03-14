"""Tests for EngineResult — CLAUDE.md §5.6 T10–T13."""
import pytest
from pydantic import ValidationError

from core.enums import EngineStatus
from core.engine_result import EngineResult
from core.deterministic_state import DeterministicState


# ---------------------------------------------------------------------------
# T10 – DeterministicState is frozen → assigning any field raises ValidationError
# ---------------------------------------------------------------------------
def test_deterministic_state_is_frozen():
    state = DeterministicState()
    with pytest.raises(ValidationError):
        state.calculations = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# T11 – status=computed + value present → is_usable == True
# ---------------------------------------------------------------------------
def test_engine_result_computed_with_value_is_usable():
    result = EngineResult[float](status=EngineStatus.COMPUTED, value=42.5)
    assert result.is_usable is True


# ---------------------------------------------------------------------------
# T12 – status=insufficient_data + value=None → is_usable == False
# ---------------------------------------------------------------------------
def test_engine_result_insufficient_data_not_usable():
    result = EngineResult[float](status=EngineStatus.INSUFFICIENT_DATA, value=None)
    assert result.is_usable is False


# ---------------------------------------------------------------------------
# T13 – status=computed + value=None → is_usable == False
# ---------------------------------------------------------------------------
def test_engine_result_computed_no_value_not_usable():
    result = EngineResult[float](status=EngineStatus.COMPUTED, value=None)
    assert result.is_usable is False
