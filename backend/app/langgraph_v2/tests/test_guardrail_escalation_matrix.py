from app.langgraph_v2.nodes.nodes_guardrail import _apply_coverage_matrix_gate


def test_guardrail_coverage_matrix_normalizes_statuses() -> None:
    coverage = {
        "api682": {"status": "human_required", "coverage": "confirmed"},
        "steam_cip_sip": {"status": "human_required", "coverage": "unknown"},
        "mixed_units": {"status": "ask_user", "coverage": "unknown"},
        "pv_limit": {"status": "critical", "coverage": "confirmed"},
    }
    rag_coverage = {
        "steam_cip_sip": {"status": "confirmed"},
    }

    out = _apply_coverage_matrix_gate(coverage, rag_coverage=rag_coverage)

    assert out["api682"]["status"] == "hard_block"
    assert out["api682"]["decision"] == "human_required"
    assert out["steam_cip_sip"]["status"] == "conditional"
    assert out["steam_cip_sip"]["decision"] == "ask_user"
    assert out["mixed_units"]["status"] == "conditional"
    assert out["mixed_units"]["decision"] == "ask_user"
    assert out["pv_limit"]["status"] == "conditional"
    assert out["pv_limit"]["pv_critical"] is True
