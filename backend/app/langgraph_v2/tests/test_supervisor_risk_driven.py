from app.langgraph_v2.nodes.nodes_supervisor import _derive_open_questions
from app.langgraph_v2.state.sealai_state import SealAIState, WorkingMemory, RequirementSpec

def test_derive_open_questions_prioritizes_shaft_runout_on_high_pressure() -> None:
    state = SealAIState(
        working_profile={
            "pressure_bar": 40.0,  # High pressure
        },
        reasoning={
            "missing_params": ["shaft_diameter"],
            "working_memory": WorkingMemory(
                material_requirements=RequirementSpec(
                    operating_conditions={"pressure_bar": 40.0},
                    missing_critical_parameters=["shaft_runout"]
                )
            )
        }
    )

    questions = _derive_open_questions(state)
    
    # shaft_diameter is in _REQUIRED_PARAMS_FOR_READY -> always high
    d_question = next(q for q in questions if q.id == "shaft_diameter")
    assert d_question.priority == "high"
    
    # shaft_runout is NOT in _REQUIRED_PARAMS_FOR_READY, 
    # but should be high due to pressure > 25 bar risk weight
    r_question = next(q for q in questions if q.id == "shaft_runout")
    assert r_question.priority == "high"
    assert "sichere technische Auslegung" in r_question.reason

def test_derive_open_questions_low_priority_for_non_critical_missing() -> None:
    state = SealAIState(
        working_profile={
            "pressure_bar": 5.0,  # Low pressure
        },
        reasoning={
            "working_memory": WorkingMemory(
                material_requirements=RequirementSpec(
                    operating_conditions={"pressure_bar": 5.0},
                    missing_critical_parameters=["shaft_runout"]
                )
            )
        }
    )

    questions = _derive_open_questions(state)
    
    r_question = next(q for q in questions if q.id == "shaft_runout")
    assert r_question.priority == "medium"
