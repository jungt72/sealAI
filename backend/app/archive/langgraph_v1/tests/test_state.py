# backend/app/langgraph/tests/test_state.py
# MIGRATION: Phase-1 - Test State (SealAIState ist ein TypedDict)

import pytest
from app.langgraph.state import (
    SealAIState,
    MetaInfo,
    compute_requirements_coverage,
    ensure_phase,
    format_requirements_summary,
    merge_rwd_requirements,
    missing_requirement_fields,
    sanitize_rwd_requirements,
    validate_slots,
)
from app.langgraph.nodes.discovery_intake import discovery_intake

def test_state_creation():
    meta = MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1")
    state = SealAIState(meta=meta)
    assert state.get("messages", []) == []
    assert state.get("slots", {}) == {}
    assert state.get("context_refs", []) == []

def test_slots_validation():
    meta = MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1")

    # Valid small slot
    state_ok = SealAIState(meta=meta, slots={"temp": 100})
    assert state_ok["slots"]["temp"] == 100
    # discovery_intake sollte ohne Exception durchlaufen
    _ = discovery_intake(state_ok)

    # Invalid large slot: validate_slots MUSS hier eine ValueError werfen
    with pytest.raises(ValueError):
        validate_slots({"big": "x" * 1001})

def test_rwd_requirements_helpers():
    payload = {
        "machine": "Aggregate",
        "application": "Radialwellendichtung",
        "medium": "Öl",
        "speed_rpm": "1500",
        "shaft_diameter": "45.5",
        "temperature_min": "-20",
        "temperature_max": "120",
    }
    sanitized = sanitize_rwd_requirements(payload)
    assert sanitized["speed_rpm"] == pytest.approx(1500.0)
    assert sanitized["shaft_diameter"] == pytest.approx(45.5)

    merged = merge_rwd_requirements({"medium": "GL-4"}, sanitized)
    assert merged["medium"] == "Öl"

    coverage = compute_requirements_coverage(merged)
    assert 0.0 < coverage <= 1.0

    missing = missing_requirement_fields(merged)
    assert isinstance(missing, list)
    assert "pressure_inner" in missing

    summary = format_requirements_summary(merged)
    assert "Maschine" in summary

    assert ensure_phase(SealAIState(), "bedarfsanalyse") == "bedarfsanalyse"
