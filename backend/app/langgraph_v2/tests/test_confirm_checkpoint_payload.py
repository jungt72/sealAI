from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.confirm_checkpoint import build_confirm_checkpoint_payload


def test_build_confirm_checkpoint_payload() -> None:
    state = SealAIState(
        phase="confirm",
        last_node="confirm_recommendation_node",
        governed_output_text="**Abnahme-Checkpoint (vorläufig)**\n- Status: GO",
        user_id="user-1",
        thread_id="conv-1",
        recommendation_go=True,
        coverage_score=0.9,
        coverage_gaps=["medium"],
        working_profile={
            "engineering_profile": {
                "medium": "Hydraulikoel",
                "temperature_C": 80,
                "pressure_bar": 10,
                "speed_rpm": 1500,
                "shaft_diameter": 50,
            }
        },
        system={
            "governance_metadata": {
                "scope_of_validity": ["Nur fuer den aktuellen Assertion-Stand."],
                "assumptions_active": [],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": ["PTFE erfordert Herstellerfreigabe."],
                "gate_failures": [],
                "governance_notes": [],
            },
            "rfq_admissibility": {
                "status": "inadmissible",
                "reason": "rfq_contract_missing",
                "open_points": [],
                "blockers": [],
                "governed_ready": False,
            },
        },
    )
    payload = build_confirm_checkpoint_payload(state, action="RUN_PANEL_NORMS_RAG", checkpoint_id="chk-1")
    assert payload["checkpoint_id"] == "chk-1"
    assert payload["required_user_sub"] == state.conversation.user_id
    assert payload["conversation_id"] == state.conversation.thread_id
    assert payload["action"] == "RUN_PANEL_NORMS_RAG"
    assert payload["risk"] == "med"
    assert payload["preview"]["text"].startswith("**Abnahme-Checkpoint")
    assert payload["preview"]["coverage_score"] == 0.9
    assert payload["preview"]["coverage_gaps"] == ["medium"]
    assert payload["preview"]["governance_metadata"]["scope_of_validity"] == ["Nur fuer den aktuellen Assertion-Stand."]
    assert payload["preview"]["rfq_admissibility"]["status"] == "inadmissible"
