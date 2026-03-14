"""
Tests for backend/app/agent/hardening/ — H01 – H26.

Field names in guard tests use the ACTUAL keys from logic.py / state.py:
  - ALLOWED: "temperature", "pressure", "speed", "diameter", "medium", "material"
  - FORBIDDEN: "governance", "cycle", "selection", "v_m_s", "pv_value",
               "release_status", "rfq_admissibility", etc.
"""
import logging
import pytest

from app.agent.hardening.enums import ExtractionCertainty, EngineStatus
from app.agent.hardening.engine_result import EngineResult
from app.agent.hardening.extraction import classify_certainty, is_calculable
from app.agent.hardening.guard import (
    claim_whitelist_check,
    snapshot_deterministic_layers,
    assert_deterministic_unchanged,
)
from app.agent.hardening.plausibility import (
    check_circumferential_speed,
    check_pv_value,
    check_temperature_range,
)


# ---------------------------------------------------------------------------
# H01 – H08: ExtractionCertainty & is_calculable
# ---------------------------------------------------------------------------


def test_H01_explicit_value_with_unit():
    """classify_certainty with explicit text + unit → EXPLICIT_VALUE."""
    result = classify_certainty(
        raw_text="150°C",
        parsed_value=150.0,
        has_explicit_unit=True,
    )
    assert result == ExtractionCertainty.EXPLICIT_VALUE


def test_H02_no_text_no_value_gives_ambiguous():
    """classify_certainty with None text and None value → AMBIGUOUS."""
    result = classify_certainty(raw_text=None, parsed_value=None)
    assert result == ExtractionCertainty.AMBIGUOUS


def test_H03_inferred_from_context():
    """classify_certainty with is_inferred=True → INFERRED_FROM_CONTEXT."""
    result = classify_certainty(
        raw_text="hot water application",
        parsed_value=95.0,
        is_inferred=True,
    )
    assert result == ExtractionCertainty.INFERRED_FROM_CONTEXT


def test_H04_explicit_range():
    """classify_certainty with is_range=True → EXPLICIT_RANGE."""
    result = classify_certainty(
        raw_text="120-180°C",
        parsed_value=None,
        is_range=True,
    )
    assert result == ExtractionCertainty.EXPLICIT_RANGE


def test_H05_ambiguous_never_calculable():
    """is_calculable(AMBIGUOUS, confirmed=True) → False."""
    assert is_calculable(ExtractionCertainty.AMBIGUOUS, confirmed=True) is False


def test_H06_inferred_unconfirmed_not_calculable():
    """is_calculable(INFERRED, confirmed=False) → False."""
    assert is_calculable(ExtractionCertainty.INFERRED_FROM_CONTEXT, confirmed=False) is False


def test_H07_inferred_confirmed_is_calculable():
    """is_calculable(INFERRED, confirmed=True) → True."""
    assert is_calculable(ExtractionCertainty.INFERRED_FROM_CONTEXT, confirmed=True) is True


def test_H08_explicit_value_calculable_without_confirmation():
    """is_calculable(EXPLICIT_VALUE, confirmed=False) → True."""
    assert is_calculable(ExtractionCertainty.EXPLICIT_VALUE, confirmed=False) is True


# ---------------------------------------------------------------------------
# H09 – H11: EngineResult
# ---------------------------------------------------------------------------


def test_H09_computed_with_value_is_usable():
    """EngineResult(status=COMPUTED, value=42.5).is_usable → True."""
    result: EngineResult[float] = EngineResult(status=EngineStatus.COMPUTED, value=42.5)
    assert result.is_usable is True


def test_H10_insufficient_data_not_usable():
    """EngineResult(status=INSUFFICIENT_DATA).is_usable → False."""
    result: EngineResult[float] = EngineResult(status=EngineStatus.INSUFFICIENT_DATA)
    assert result.is_usable is False


def test_H11_computed_but_none_value_not_usable():
    """EngineResult(status=COMPUTED, value=None).is_usable → False."""
    result: EngineResult[float] = EngineResult(status=EngineStatus.COMPUTED, value=None)
    assert result.is_usable is False


# ---------------------------------------------------------------------------
# H12 – H16: Guard — claim whitelist
# ---------------------------------------------------------------------------


def test_H12_allowed_temperature_passes():
    """claim_whitelist_check({'temperature': 150}) → {'temperature': 150}."""
    result = claim_whitelist_check({"temperature": 150})
    assert result == {"temperature": 150}


def test_H13_hard_stops_stripped_with_critical_log(caplog):
    """claim_whitelist_check({'hard_stops': [...]}) → {} and logs CRITICAL."""
    with caplog.at_level(logging.CRITICAL, logger="app.agent.hardening.guard"):
        result = claim_whitelist_check({"hard_stops": ["blocked"]})
    assert result == {}
    assert any("GUARD VIOLATION" in rec.message for rec in caplog.records)


def test_H14_governance_layer_stripped_with_critical_log(caplog):
    """claim_whitelist_check({'governance': {...}}) → {} and logs CRITICAL."""
    with caplog.at_level(logging.CRITICAL, logger="app.agent.hardening.guard"):
        result = claim_whitelist_check({"governance": {"release_status": "rfq_ready"}})
    assert result == {}
    assert any("GUARD VIOLATION" in rec.message for rec in caplog.records)


def test_H15_mixed_allowed_and_forbidden():
    """Only allowed key survives when mixed with a forbidden key."""
    result = claim_whitelist_check({"temperature": 150, "v_m_s": 5.0})
    assert result == {"temperature": 150}
    assert "v_m_s" not in result


def test_H16_unknown_field_stripped_with_warning(caplog):
    """claim_whitelist_check({'totally_unknown_field': 'x'}) → {} and logs WARNING."""
    with caplog.at_level(logging.WARNING, logger="app.agent.hardening.guard"):
        result = claim_whitelist_check({"totally_unknown_field_xyz": "x"})
    assert result == {}
    assert any("GUARD" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# H17 – H19: Guard — invariant check
# ---------------------------------------------------------------------------


def _make_sealing_state(governance_extra: dict | None = None) -> dict:
    """Build a minimal sealing state dict for invariant tests."""
    state = {
        "governance": {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "scope_of_validity": [],
            "assumptions_active": [],
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        },
        "cycle": {
            "analysis_cycle_id": "test_1",
            "state_revision": 1,
            "snapshot_parent_revision": 0,
            "superseded_by_cycle": None,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
        },
        "selection": {
            "selection_status": "not_started",
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "winner_candidate_id": None,
            "recommendation_artifact": None,
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
        },
    }
    if governance_extra:
        state["governance"].update(governance_extra)
    return state


def test_H17_unchanged_state_no_exception():
    """snapshot before == snapshot after → no RuntimeError raised."""
    state = _make_sealing_state()
    before = snapshot_deterministic_layers(state)
    # Nothing changes
    assert_deterministic_unchanged(before, state, node_name="test_node")


def test_H18_governance_mutation_raises():
    """Modifying governance layer between snapshots → RuntimeError."""
    state = _make_sealing_state()
    before = snapshot_deterministic_layers(state)
    # Simulate LLM mutating governance
    state["governance"]["release_status"] = "rfq_ready"
    with pytest.raises(RuntimeError, match="CRITICAL INVARIANT VIOLATION"):
        assert_deterministic_unchanged(before, state, node_name="evidence_tool_node")


def test_H19_selection_mutation_raises():
    """Modifying selection layer between snapshots → RuntimeError."""
    state = _make_sealing_state()
    before = snapshot_deterministic_layers(state)
    # Simulate LLM mutating selection
    state["selection"]["winner_candidate_id"] = "nbr_candidate_1"
    with pytest.raises(RuntimeError, match="CRITICAL INVARIANT VIOLATION"):
        assert_deterministic_unchanged(before, state, node_name="reasoning_node")


# ---------------------------------------------------------------------------
# H20 – H26: Plausibility checks
# ---------------------------------------------------------------------------


def test_H20_valid_circumferential_speed():
    """check_circumferential_speed(15.0) → COMPUTED."""
    result = check_circumferential_speed(15.0)
    assert result.status == EngineStatus.COMPUTED
    assert result.is_usable is True


def test_H21_excessive_circumferential_speed():
    """check_circumferential_speed(200.0) → OUT_OF_RANGE."""
    result = check_circumferential_speed(200.0)
    assert result.status == EngineStatus.OUT_OF_RANGE
    assert result.is_usable is False


def test_H22_negative_circumferential_speed():
    """check_circumferential_speed(-5.0) → CONTRADICTION_DETECTED."""
    result = check_circumferential_speed(-5.0)
    assert result.status == EngineStatus.CONTRADICTION_DETECTED
    assert result.is_usable is False


def test_H23_valid_pv_value():
    """check_pv_value(50.0) → COMPUTED."""
    result = check_pv_value(50.0)
    assert result.status == EngineStatus.COMPUTED
    assert result.is_usable is True


def test_H24_excessive_pv_value():
    """check_pv_value(600.0) → OUT_OF_RANGE."""
    result = check_pv_value(600.0)
    assert result.status == EngineStatus.OUT_OF_RANGE
    assert result.is_usable is False


def test_H25_temperature_range_contradiction():
    """check_temperature_range(150, 100) → CONTRADICTION_DETECTED (min > max)."""
    result = check_temperature_range(150, 100)
    assert result.status == EngineStatus.CONTRADICTION_DETECTED
    assert result.is_usable is False


def test_H26_valid_temperature_range():
    """check_temperature_range(20, 200) → COMPUTED."""
    result = check_temperature_range(20, 200)
    assert result.status == EngineStatus.COMPUTED
    assert result.is_usable is True
