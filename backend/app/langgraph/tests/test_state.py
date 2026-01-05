# MIGRATION: Phase-1 - Test State

import pytest
from ..state import SealAIState, MetaInfo

def test_state_creation():
    meta = MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1")
    state = SealAIState(meta=meta)
    assert state.messages == []
    assert state.slots == {}
    assert state.context_refs == []

def test_slots_validation():
    meta = MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1")
    # Valid small slot
    state = SealAIState(meta=meta, slots={"temp": 100})
    assert state.slots["temp"] == 100

    # Invalid large slot
    with pytest.raises(ValueError):
        SealAIState(meta=meta, slots={"big": "x" * 1001})