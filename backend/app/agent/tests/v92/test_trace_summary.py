"""TraceSummary contract tests (Blueprint §6.1 / §11.7 / §25.1).

Confirms the unified trace schema formalizes the trace dicts already emitted by
the runtime (single source of truth), tolerates partial/extra keys, and exposes
the §25.1 quality/alert signals. Additive, test-only.
"""

from __future__ import annotations

from app.agent.communication.mobile_triage import build_mobile_leakage_triage
from app.agent.v92.contracts import TraceSummary


def test_trace_summary_defaults_are_safe() -> None:
    ts = TraceSummary()
    assert ts.llm_used is False
    assert ts.rag_used is False
    assert ts.graph_used is False
    assert ts.empty_spinner_violated is False
    assert ts.agents_run == []
    assert ts.action_chips_shown == 0


def test_trace_summary_validates_existing_mobile_emitter() -> None:
    # The mobile leakage triage envelope is a real emitter; its trace dict must
    # validate against the unified schema unchanged.
    env = build_mobile_leakage_triage(has_attachment=True)
    ts = TraceSummary.from_trace(env.trace)
    assert ts.route == "mobile_leakage_triage"
    assert ts.tier == 2
    assert ts.mobile_surface is True
    assert ts.empty_spinner_violated is False
    assert ts.rag_used is False and ts.graph_used is False


def test_trace_summary_allows_extra_keys() -> None:
    ts = TraceSummary.from_trace({"route": "smalltalk", "some_future_key": 123})
    dumped = ts.model_dump()
    assert dumped["route"] == "smalltalk"
    assert dumped["some_future_key"] == 123  # extra="allow" keeps forward-compat


def test_trace_summary_exposes_quality_signals() -> None:
    ts = TraceSummary.from_trace(
        {
            "forbidden_phrase_detected": True,
            "rfq_readiness": "RFQ_WITH_OPEN_POINTS",
            "case_revision": 7,
            "action_chip_selected": True,
            "rfq_one_pager_generated": True,
        }
    )
    assert ts.forbidden_phrase_detected is True
    assert ts.rfq_readiness == "RFQ_WITH_OPEN_POINTS"
    assert ts.case_revision == 7
    assert ts.action_chip_selected is True
    assert ts.rfq_one_pager_generated is True
