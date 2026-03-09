import pytest
from app.langgraph_v2.state.sealai_state import SealAIState, GroundedFact
from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import _extract_grounded_facts_for_material

def test_grounding_divergence_detection():
    # Setup state with multiple sources providing different values for the same fact
    state = SealAIState(
        reasoning={
            "working_memory": {
                "panel_material": {
                    "technical_docs": [
                        {
                            "text": "FKM temp source 1",
                            "metadata": {
                                "material_code": "FKM",
                                "document_id": "DOC-HIGH-RANK",
                                "temp_range": {"min_c": -20, "max_c": 200}
                            },
                            "score": 0.9
                        },
                        {
                            "text": "FKM temp source 2 (divergent)",
                            "metadata": {
                                "material_code": "FKM",
                                "document_id": "DOC-LOW-RANK",
                                "temp_range": {"min_c": -10, "max_c": 180}
                            },
                            "score": 0.7
                        },
                        {
                            "text": "FKM temp source 3 (same as 1, should be deduped)",
                            "metadata": {
                                "material_code": "FKM",
                                "document_id": "DOC-SAME-VALUE",
                                "temp_range": {"min_c": -20, "max_c": 200}
                            },
                            "score": 0.5
                        }
                    ]
                }
            }
        }
    )
    
    facts = _extract_grounded_facts_for_material(state, "FKM")
    
    # Should only have 1 primary fact type (Temperature Range)
    assert len(facts) == 1
    
    primary = facts[0]
    assert primary.name == "Temperature Range"
    assert primary.value == "-20 to 200"
    assert primary.source == "DOC-HIGH-RANK"
    
    # Divergence should be detected
    assert primary.is_divergent is True
    assert len(primary.variants) == 1
    assert primary.variants[0].value == "-10 to 180"
    assert primary.variants[0].source == "DOC-LOW-RANK"

def test_grounding_no_divergence_for_same_values():
    state = SealAIState(
        reasoning={
            "working_memory": {
                "panel_material": {
                    "technical_docs": [
                        {
                            "text": "FKM source A",
                            "metadata": {
                                "material_code": "FKM",
                                "document_id": "DOC-A",
                                "shore_hardness": 75
                            },
                            "score": 0.8
                        },
                        {
                            "text": "FKM source B (same value)",
                            "metadata": {
                                "material_code": "FKM",
                                "document_id": "DOC-B",
                                "shore_hardness": 75
                            },
                            "score": 0.6
                        }
                    ]
                }
            }
        }
    )
    
    facts = _extract_grounded_facts_for_material(state, "FKM")
    assert len(facts) == 1
    assert facts[0].is_divergent is False
    assert len(facts[0].variants) == 0
