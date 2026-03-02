from __future__ import annotations

import hashlib

from langchain_core.messages import HumanMessage

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


def test_extracted_rpm_and_shaft_aliases_flow_into_contract_parameters() -> None:
    state = SealAIState(
        extracted_params={
            "rpm": 1450.0,
            "shaft_d1_mm": 55.0,
        }
    )

    patch = node_prepare_contract(state)
    contract = patch["answer_contract"]
    allowed_tokens = set(patch["flags"].get("answer_subgraph_allowed_number_tokens") or [])

    assert contract.resolved_parameters.get("rpm") == 1450.0
    assert contract.resolved_parameters.get("shaft_d1_mm") == 55.0
    assert contract.resolved_parameters.get("speed_rpm") == 1450.0
    assert contract.resolved_parameters.get("shaft_diameter") == 55.0
    assert "1450.0" in allowed_tokens
    assert "55.0" in allowed_tokens


def test_prepare_contract_allowlists_live_calc_and_rounded_numbers() -> None:
    state = SealAIState(
        extracted_params={"rpm": 1500, "hrc_value": 40},
        live_calc_tile={
            "v_surface_m_s": 3.92,
            "pv_value_mpa_m_s": 117.8,
            "hrc_value": 40.0,
            "parameters": {"rpm": 1500, "hrc_value": 40},
            "status": "warning",
        },
        calculation_result={"recommended_hardness_hrc": 58.0},
    )

    patch = node_prepare_contract(state)
    allowed_tokens = set(patch["flags"].get("answer_subgraph_allowed_number_tokens") or [])

    assert "1500" in allowed_tokens
    assert "40" in allowed_tokens
    assert "58" in allowed_tokens
    assert "118" in allowed_tokens
    assert "3.92" in allowed_tokens
    assert "117.8" in allowed_tokens


def test_prepare_contract_moves_seal_compound_out_of_material_and_sets_seal_material() -> None:
    state = SealAIState(
        extracted_params={"material": "PTFE"},
        material_choice={"material": "PTFE"},
    )

    patch = node_prepare_contract(state)
    contract = patch["answer_contract"]

    assert contract.resolved_parameters.get("seal_material") == "PTFE"
    assert contract.resolved_parameters.get("material") is None


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


def test_extreme_temperature_query_injects_required_factcards(monkeypatch) -> None:
    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        if "PTFE-F-008" in query:
            return {
                "hits": [
                    {
                        "snippet": "FactCard PTFE-F-008: PTFE remains usable at cryogenic temperatures with design controls.",
                        "source": "ptfe_factcards",
                        "document_id": "PTFE-F-008",
                        "metadata": {"id": "PTFE-F-008", "doc_type": "ptfe_factcard"},
                        "score": 0.99,
                    }
                ]
            }
        if "PTFE-F-062" in query:
            return {
                "hits": [
                    {
                        "snippet": "FactCard PTFE-F-062: sealing requires spring-energization/preload because PTFE creeps.",
                        "source": "ptfe_factcards",
                        "document_id": "PTFE-F-062",
                        "metadata": {"id": "PTFE-F-062", "doc_type": "ptfe_factcard"},
                        "score": 0.98,
                    }
                ]
            }
        return {"hits": []}

    monkeypatch.setattr("app.mcp.knowledge_tool.search_technical_docs", _fake_search_technical_docs)

    state = SealAIState(
        parameters=TechnicalParameters(temperature_C=-200.0),
        messages=[HumanMessage(content="Ist PTFE bei -200°C noch einsetzbar?")],
        flags={"frontdoor_intent_category": "ENGINEERING_CALCULATION"},
    )

    patch = node_prepare_contract(state)
    final_prompt = patch["final_prompt"]
    selected_fact_ids = patch["answer_contract"].selected_fact_ids

    assert "PTFE-F-008" in final_prompt
    assert "PTFE-F-062" in final_prompt
    assert any("PTFE-F-008" in item for item in selected_fact_ids)
    assert any("PTFE-F-062" in item for item in selected_fact_ids)
