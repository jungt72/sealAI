from __future__ import annotations

import math

import pytest

from app.services.rfq.report_builder import build_rfq_report, canonical_json


def _base_state() -> dict:
    return {
        "rfq_ready": True,
        "guardrail_escalation_level": "none",
        "failure_evidence_missing": False,
        "assumption_lock_hash": "h-1",
        "assumption_lock_hash_confirmed": "h-1",
        "conversation_track": "design",
        "parameters": {
            "pressure_bar": 10.0,
            "speed_rpm": 1200.0,
            "shaft_diameter": 50.0,
            "medium": "water",
        },
        "assumption_list": [
            {
                "id": "1",
                "text": "Shaft hardness assumed >=55 HRC",
                "impact": "high",
                "source": "inferred",
                "requires_confirmation": True,
            }
        ],
        "pending_assumptions": [],
        "assumptions_confirmed": True,
        "risk_heatmap": {"pv_limit": "critical", "mixed_units": "low"},
        "guardrail_coverage": {
            "pv_limit": {
                "status": "critical",
                "value": 31.4159,
                "limit": 30.0,
                "ratio": 1.0472,
                "reason": "PV ratio computed from pressure, speed, and diameter.",
            },
            "mixed_units": {"status": "confirmed", "reason": "Units provided in SI."},
        },
        "guardrail_rag_coverage": {"pv_limit": {"status": "confirmed", "hits": 1}},
        "recommendation": {
            "seal_family": "rotary_lip",
            "material": "FKM",
            "profile": "SC",
            "summary": "Directional recommendation under confirmed assumptions.",
            "risk_hints": ["Critical PV margin."],
        },
        "sources": [{"source": "kb/doc-1", "metadata": {"tenant_id": "tenant-1"}, "snippet": "PV guidance"}],
    }


def test_rfq_report_builder_shape_and_hash_deterministic() -> None:
    state = _base_state()
    report_a = build_rfq_report(
        state=state,
        chat_id="chat-1",
        checkpoint_thread_id="tenant-1:user-1:chat-1",
        tenant_id="tenant-1",
        user_id="user-1",
        now_ts=1700000000.0,
    )
    report_b = build_rfq_report(
        state=state,
        chat_id="chat-1",
        checkpoint_thread_id="tenant-1:user-1:chat-1",
        tenant_id="tenant-1",
        user_id="user-1",
        now_ts=1700000000.0,
    )

    assert report_a["meta"]["schema_version"] == "2.0"
    assert report_a["meta"]["rfq_ready"] is True
    assert report_a["meta"]["assumption_lock_hash"] == "h-1"
    assert report_a["meta"]["report_hash"]
    assert report_a["assumptions"]["list"][0]["id"] == "1"
    assert report_a["risk"]["guardrail_escalation_level"] == "none"
    assert report_a["coverage"]["guardrail_coverage"]["pv_limit"]["status"] == "critical"
    assert canonical_json(report_a) == canonical_json(report_b)


def test_rfq_report_builder_pv_calculation() -> None:
    report = build_rfq_report(
        state=_base_state(),
        chat_id="chat-1",
        checkpoint_thread_id="tenant-1:user-1:chat-1",
        tenant_id="tenant-1",
        user_id="user-1",
        now_ts=1700000000.0,
    )
    pv = report["calculated_checks"]["pv"]
    expected_v = math.pi * (0.05) * 1200.0 / 60.0
    expected_pv = 10.0 * expected_v
    assert pv["available"] is True
    assert pv["pressure_bar"] == 10.0
    assert pv["speed_rpm"] == 1200.0
    assert pv["diameter_mm"] == 50.0
    assert pv["surface_speed_mps"] == pytest.approx(expected_v, rel=1e-6)
    assert pv["pv"] == pytest.approx(expected_pv, rel=1e-6)


def test_rfq_report_builder_gate_enforced() -> None:
    state = _base_state()
    state["rfq_ready"] = False
    with pytest.raises(ValueError):
        build_rfq_report(
            state=state,
            chat_id="chat-1",
            checkpoint_thread_id="tenant-1:user-1:chat-1",
            tenant_id="tenant-1",
            user_id="user-1",
            now_ts=1700000000.0,
        )
