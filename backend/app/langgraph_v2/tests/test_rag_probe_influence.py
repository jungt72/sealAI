from app.langgraph_v2.nodes import nodes_guardrail
from app.langgraph_v2.state import SealAIState, TechnicalParameters


def test_rag_probe_downgrades_steam_escalation_to_ask_user(monkeypatch) -> None:
    monkeypatch.setattr(
        nodes_guardrail,
        "_probe_rag_coverage",
        lambda **_kwargs: {"status": "confirmed", "reason": "ok", "hits": 2, "top_sources": [{"source": "tenant-doc"}]},
    )

    state = SealAIState(
        tenant_id="tenant-1",
        parameters=TechnicalParameters(medium="steam", temperature_C=135.0),
    )

    coverage, rag_coverage, escalation_reason, questions, _recommendation = nodes_guardrail._apply_rag_coverage_cross_check(
        state,
        text="steam 135C",
        medium="steam",
        guardrail_coverage={
            "steam_cip_sip": {
                "status": "human_required",
                "coverage": "unknown",
                "reason": "Steam >120C without peak duration",
            }
        },
        escalation_reason="steam_cip_sip:human_required",
        guardrail_questions=[],
    )

    assert coverage["steam_cip_sip"]["status"] == "ask_user"
    assert coverage["steam_cip_sip"]["coverage"] == "conditional"
    assert escalation_reason == "steam_cip_sip:ask_user"
    assert "steam_cip_sip" in rag_coverage
    assert isinstance(questions, list)
