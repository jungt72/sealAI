from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.nodes_assumption_lock import assumption_lock_node
from app.langgraph_v2.state import SealAIState, TechnicalParameters


def test_assumption_hash_mismatch_forces_reconfirmation() -> None:
    baseline = SealAIState(
        messages=[HumanMessage(content="confirm #1")],
        tenant_id="tenant-1",
        parameters=TechnicalParameters(medium="steam", temperature_C=135.0),
        guardrail_coverage={"steam_cip_sip": {"status": "human_required", "coverage": "unknown"}},
        flags={"risk_level": "critical"},
    )
    baseline_patch = assumption_lock_node(baseline)
    confirmed_hash = baseline_patch["assumption_lock_hash_confirmed"]

    changed = SealAIState(
        messages=[HumanMessage(content="ok")],
        tenant_id="tenant-1",
        parameters=TechnicalParameters(medium="steam", temperature_C=135.0),
        guardrail_coverage={
            "steam_cip_sip": {"status": "human_required", "coverage": "unknown"},
            "gas_decompression": {"status": "human_required", "coverage": "unknown"},
        },
        flags={"risk_level": "critical"},
        assumption_lock_hash_confirmed=str(confirmed_hash),
        last_node="assumption_lock_node",
        pending_assumptions=["1"],
    )

    changed_patch = assumption_lock_node(changed)

    assert changed_patch["assumptions_confirmed"] is False
    assert changed_patch["assumption_lock_hash"] != confirmed_hash
    assert changed_patch["assumption_lock_hash_confirmed"] is None
    assert changed_patch["rfq_ready"] is False
