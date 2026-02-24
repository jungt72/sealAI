from __future__ import annotations

import hashlib

from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app.langgraph_v2.state.sealai_state import SealAIState, TechnicalParameters, WorkingMemory


def _contract_hash(contract) -> str:
    return hashlib.sha256(contract.model_dump_json().encode()).hexdigest()


def test_evidence_authority_prefers_din_norm_pressure_truth() -> None:
    state = SealAIState(
        working_memory=WorkingMemory(
            panel_material={
                "technical_docs": [
                    {
                        "text": "Max Druck 100 bar",
                        "source": "Forum/Unknown",
                        "metadata": {
                            "document_id": "forum_doc",
                            "chunk_id": "c1",
                            "source_type": "forum",
                        },
                        "score": 0.95,
                    },
                    {
                        "text": "Max Druck 80 bar",
                        "source": "DIN-Norm",
                        "metadata": {
                            "document_id": "din_doc",
                            "chunk_id": "c2",
                            "source_type": "DIN standard",
                        },
                        "score": 0.40,
                    },
                ]
            }
        )
    )

    patch = node_prepare_contract(state)
    contract = patch["answer_contract"]

    assert contract.resolved_parameters.get("pressure_bar") == 80.0
    final_prompt = patch["final_prompt"]
    assert "Max Druck 80 bar" in final_prompt
    assert final_prompt.find("Max Druck 80 bar") < final_prompt.find("Max Druck 100 bar")


def test_smalltalk_heuristic_when_no_params_and_no_rag_chunks() -> None:
    state = SealAIState()

    patch = node_prepare_contract(state)
    contract = patch["answer_contract"]

    assert contract.resolved_parameters.get("response_style") == "friendly_greeting"
    assert contract.calc_results.get("message_type") == "smalltalk"
    assert contract.selected_fact_ids == ["friendly_greeting"]
    assert contract.respond_with_uncertainty is False


def test_parameter_patching_copies_user_parameters_into_contract() -> None:
    state = SealAIState(parameters=TechnicalParameters(medium="Wasser"))

    patch = node_prepare_contract(state)
    contract = patch["answer_contract"]

    assert contract.resolved_parameters.get("medium") == "Wasser"


def test_contract_hash_integrity_identical_vs_minimal_change() -> None:
    base_state = SealAIState(
        working_memory=WorkingMemory(
            panel_material={
                "technical_docs": [
                    {
                        "text": "Max Druck 80 bar",
                        "source": "DIN-Norm",
                        "metadata": {"document_id": "din_doc", "chunk_id": "c2", "source_type": "DIN"},
                    }
                ]
            }
        ),
        parameters=TechnicalParameters(medium="Wasser"),
    )

    patch_a = node_prepare_contract(base_state)
    patch_b = node_prepare_contract(base_state)

    hash_a = patch_a["flags"]["answer_contract_hash"]
    hash_b = patch_b["flags"]["answer_contract_hash"]
    assert hash_a == hash_b
    assert hash_a == _contract_hash(patch_a["answer_contract"])
    assert hash_b == _contract_hash(patch_b["answer_contract"])

    changed_state = SealAIState(
        working_memory=WorkingMemory(
            panel_material={
                "technical_docs": [
                    {
                        "text": "Max Druck 80 bar",
                        "source": "DIN-Norm",
                        "metadata": {"document_id": "din_doc", "chunk_id": "c3", "source_type": "DIN"},
                    }
                ]
            }
        ),
        parameters=TechnicalParameters(medium="Wasser"),
    )
    patch_changed = node_prepare_contract(changed_state)
    changed_hash = patch_changed["flags"]["answer_contract_hash"]

    assert changed_hash != hash_a
