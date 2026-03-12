from app.agent.agent.graph import app, entry_router
from app.agent.cli import create_initial_state
from langchain_core.messages import HumanMessage


def test_entry_router_prefers_rwdr_orchestration_when_flow_is_active():
    state = {
        "messages": [HumanMessage(content="RWDR starten")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
    }
    state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "collected_fields": {
                "motion_type": "single_direction_rotation",
            },
        }
    }

    assert entry_router(state) == "rwdr_orchestration_node"


def test_graph_runs_rwdr_orchestration_path_without_llm():
    state = {
        "messages": [HumanMessage(content="RWDR strukturiert")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
    }
    state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "collected_fields": {
                "motion_type": "single_direction_rotation",
                "shaft_diameter_mm": 35.0,
                "max_speed_rpm": 1000.0,
                "pressure_profile": "pressureless_vented",
                "inner_lip_medium_scenario": "oil_bath",
                "maintenance_mode": "new_shaft",
                "external_contamination_class": "clean_room_dust",
                "installation_over_edges_flag": False,
                "vertical_shaft_flag": False,
                "confidence": {
                    "motion_type": "known",
                    "shaft_diameter_mm": "known",
                    "max_speed_rpm": "known",
                    "maintenance_mode": "known",
                    "pressure_profile": "known",
                    "external_contamination_class": "known",
                    "medium_level_relative_to_seal": "known",
                },
            },
        }
    }

    final_state = app.invoke(state)

    assert final_state["sealing_state"]["rwdr"]["flow"]["decision_executed"] is True
    assert final_state["sealing_state"]["rwdr"]["output"].type_class == "standard_rwdr"
    assert "RWDR preselection ready" in final_state["messages"][-1].content


def test_graph_consumes_simple_human_answer_for_missing_rwdr_field():
    state = {
        "messages": [HumanMessage(content="3000 U/min")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
    }
    state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "stage": "stage_1",
            "next_field": "max_speed_rpm",
            "missing_fields": ["max_speed_rpm"],
            "collected_fields": {
                "motion_type": "single_direction_rotation",
                "shaft_diameter_mm": 35.0,
                "pressure_profile": "pressureless_vented",
                "inner_lip_medium_scenario": "oil_bath",
                "maintenance_mode": "new_shaft",
            },
        }
    }

    final_state = app.invoke(state)

    assert final_state["sealing_state"]["rwdr"]["draft"].max_speed_rpm == 3000.0
    assert final_state["sealing_state"]["rwdr"]["flow"]["stage"] == "stage_2"
    assert "RWDR field accepted: max_speed_rpm" in final_state["messages"][-1].content
