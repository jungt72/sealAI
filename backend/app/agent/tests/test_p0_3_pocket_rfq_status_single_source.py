"""P0-3 (amended): the streamed Pocket Cockpit rfq_status must be single-source.

The pocket rfq_status must reflect the case's *real* RFQ readiness — the same
``evaluate_rfq_readiness`` source of truth the REST one-pager / desktop use — and
never a second, hardcoded value. Status vocabulary stays within
``RFQ_READINESS_BANDS`` (DRAFT / MINIMAL_RFQ / RFQ_WITH_OPEN_POINTS /
MANUFACTURER_REVIEW_READY / OUT_OF_SCOPE); no new suitability/release wording.

Red-before-green:
* the state→status helper does not exist yet (call-site authoritative source);
* the builder cannot yet accept the authoritative status (it hardcodes DRAFT).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agent.communication.rfq_one_pager import evaluate_rfq_readiness


def _assertion(value):
    return SimpleNamespace(asserted_value=value, confidence="confirmed")


_CORE_FIELDS = (
    "sealing_function",
    "shaft_diameter_d1_mm",
    "housing_bore_D_mm",
    "seal_width_b_mm",
    "application",
    "inside_medium",
    "request_goal",
)


def _state_with_full_core(*, blocking_missing=()):
    completeness = SimpleNamespace(
        blocking_missing_fields=list(blocking_missing),
        readiness_band="rfq_with_open_points",
    )
    return SimpleNamespace(
        asserted=SimpleNamespace(assertions={f: _assertion("x") for f in _CORE_FIELDS}),
        normalized=SimpleNamespace(parameters={}),
        engineering=SimpleNamespace(completeness_matrix=completeness),
    )


def test_state_status_helper_reflects_real_readiness_not_hardcoded_draft():
    from app.agent.v92.dashboard_contract import pocket_rfq_status_from_state

    state = _state_with_full_core()
    status = pocket_rfq_status_from_state(state)
    expected = evaluate_rfq_readiness(list(_CORE_FIELDS)).status
    assert status == expected
    # core complete -> the SoT must NOT return the hardcoded "DRAFT" default.
    assert status != "DRAFT"


def test_state_status_helper_returns_none_without_active_case():
    from app.agent.v92.dashboard_contract import pocket_rfq_status_from_state

    empty = SimpleNamespace(
        asserted=SimpleNamespace(assertions={}),
        normalized=SimpleNamespace(parameters={}),
    )
    assert pocket_rfq_status_from_state(empty) is None


def test_state_status_helper_critical_open_point_is_with_open_points():
    from app.agent.v92.dashboard_contract import pocket_rfq_status_from_state

    state = _state_with_full_core(blocking_missing=[{"key": "shaft_condition_known"}])
    assert pocket_rfq_status_from_state(state) == "RFQ_WITH_OPEN_POINTS"


def test_builder_accepts_authoritative_rfq_status_override():
    from app.services.rwdr_mvp_brief import build_rwdr_p0_pocket_cockpit_patch

    text = "RWDR / Wellendichtring undicht am Getriebe, Welle 80x100x10, Medium Öl."
    result = build_rwdr_p0_pocket_cockpit_patch(text, rfq_status="RFQ_WITH_OPEN_POINTS")
    assert result is not None
    patch, _chips = result
    # The authoritative case status wins over the builder's text-derived default.
    assert patch.rfq_status == "RFQ_WITH_OPEN_POINTS"


def test_builder_default_status_comes_from_the_single_source_not_a_hardcode():
    # Without an override the builder derives via the SoT on its own candidates
    # (text can't complete the core -> DRAFT), never a literal hardcode.
    from app.services.rwdr_mvp_brief import (
        build_rwdr_p0_pocket_cockpit_patch,
        _extract_rwdr_candidate_fields,
    )

    text = "RWDR / Wellendichtring undicht am Getriebe, Welle 80x100x10, Medium Öl."
    result = build_rwdr_p0_pocket_cockpit_patch(text)
    assert result is not None
    patch, _chips = result
    fields = [f["field"] for f in _extract_rwdr_candidate_fields(text)]
    assert patch.rfq_status == evaluate_rfq_readiness(fields).status
