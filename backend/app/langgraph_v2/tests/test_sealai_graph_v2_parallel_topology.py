from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

import app.langgraph_v2.sealai_graph_v2 as graph_module
from app.langgraph_v2.state import SealAIState


def test_graph_uses_parallel_analysis_fanout_and_merge() -> None:
    builder = graph_module.create_sealai_graph_v2(
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
        return_builder=True,
    )
    node_ids = set(builder.nodes.keys())

    assert "material_analysis_node" in node_ids
    assert "mechanical_analysis_node" in node_ids
    assert "merge_analysis_node" in node_ids
    assert "knowledge_agent_node" in node_ids
    assert "node_p4_live_calc" not in node_ids

    outbound = {(source, target) for source, target in builder.edges}
    assert ("node_p1_context", "material_analysis_node") in outbound
    assert ("node_p1_context", "mechanical_analysis_node") in outbound
    assert ("material_analysis_node", "merge_analysis_node") in outbound
    assert ("mechanical_analysis_node", "merge_analysis_node") in outbound
    assert ("merge_analysis_node", "final_answer_node") in outbound
    assert ("node_p1_context", "knowledge_agent_node") not in outbound
    assert ("human_review_node", "worm_evidence_node") in outbound
    assert ("request_clarification_node", "worm_evidence_node") in outbound
    assert ("reasoning_core_node", "final_answer_node") in outbound


def test_frontdoor_dispatch_routes_material_research_to_supervisor() -> None:
    state = SealAIState(
        conversation={"intent": {"goal": "explanation_or_comparison"}},
        reasoning={
            "requires_rag": True,
            "flags": {"frontdoor_intent_category": "MATERIAL_RESEARCH"},
        },
    )

    assert graph_module._frontdoor_dispatch(state) == "knowledge"


def test_frontdoor_dispatch_keeps_engineering_turn_on_parallel_analysis() -> None:
    state = SealAIState(
        conversation={"intent": {"goal": "design_recommendation"}},
        reasoning={
            "requires_rag": False,
            "flags": {"frontdoor_intent_category": "ENGINEERING_CALCULATION"},
        },
    )

    assert graph_module._frontdoor_dispatch(state) == "analysis"


def test_knowledge_followup_dispatch_prefers_response_when_text_exists() -> None:
    state = SealAIState(
        conversation={"intent": {"goal": "explanation_or_comparison"}},
        system={"final_text": "Kyrolon ist ein PTFE-Compound."},
    )

    assert graph_module._knowledge_followup_dispatch(state) == "response"


def test_knowledge_followup_dispatch_falls_back_to_finalize_without_text() -> None:
    state = SealAIState()

    assert graph_module._knowledge_followup_dispatch(state) == "finalize"


def test_knowledge_followup_dispatch_keeps_troubleshooting_on_finalize_even_with_text() -> None:
    state = SealAIState(
        conversation={"intent": {"goal": "troubleshooting_leakage"}},
        system={"final_text": "Vorlaeufige Wissensantwort."},
    )

    assert graph_module._knowledge_followup_dispatch(state) == "finalize"


def test_knowledge_followup_dispatch_uses_material_research_fast_path_from_flag() -> None:
    state = SealAIState(
        reasoning={"flags": {"frontdoor_intent_category": "MATERIAL_RESEARCH"}},
        system={"final_text": "Kyrolon ist ein PTFE-Compound."},
    )

    assert graph_module._knowledge_followup_dispatch(state) == "response"


def _raise_material(*_args, **_kwargs):
    raise RuntimeError("material branch failed")


def _raise_mechanical(*_args, **_kwargs):
    raise RuntimeError("mechanical branch failed")


def test_parallel_branch_wrappers_capture_partial_failures(monkeypatch) -> None:
    monkeypatch.setattr(graph_module, "material_agent_node", _raise_material)
    monkeypatch.setattr(graph_module, "node_p4_live_calc", _raise_mechanical)

    state = SealAIState()

    material_patch = asyncio.run(graph_module._material_analysis_node(state))
    mechanical_patch = asyncio.run(graph_module._mechanical_analysis_node(state))

    assert material_patch["reasoning"]["diagnostic_data"]["parallel_branches"]["material_analysis"]["status"] == "error"
    assert mechanical_patch["reasoning"]["diagnostic_data"]["parallel_branches"]["mechanical_analysis"]["status"] == "error"


def test_merge_analysis_node_propagates_partial_failure_to_system_error() -> None:
    state = SealAIState(
        reasoning={
            "diagnostic_data": {
                "parallel_branches": {
                    "material_analysis": {"status": "error"},
                    "mechanical_analysis": {"status": "ok"},
                }
            }
        }
    )

    patch = graph_module._merge_analysis_node(state)

    assert patch["reasoning"]["diagnostic_data"]["parallel_merge"]["status"] == "partial_failure"
    assert patch["system"]["error"] == "partial_expert_failure"
