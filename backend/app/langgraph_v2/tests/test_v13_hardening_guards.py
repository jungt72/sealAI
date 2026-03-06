from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import app.langgraph_v2.sealai_graph_v2 as graph_module
from app.langgraph_v2.nodes.response_node import response_node
from app.langgraph_v2.state import SealAIState
from app.services.fast_brain.router import FastBrainRouter
from app.services.rag.nodes.p1_context import _P1Extraction, node_p1_context


def test_p1_context_new_case_isolation() -> None:
    state = SealAIState(
        conversation={
            "messages": [HumanMessage(content="Neue Anfrage ohne verwertbare Parameter")],
            "router_classification": "new_case",
        },
        working_profile={
            "engineering_profile": {
                "medium": "Hydraulikoel",
                "pressure_max_bar": 250.0,
                "temperature_max_c": 120.0,
            },
            "extracted_params": {
                "medium": "Hydraulikoel",
                "pressure_max_bar": 250.0,
                "temperature_max_c": 120.0,
                "hrc_value": 58.0,
            },
        },
    )

    with patch("app.services.rag.nodes.p1_context._invoke_extraction", return_value=_P1Extraction()):
        command = node_p1_context(state)

    result = command.update
    engineering_profile = result["working_profile"]["engineering_profile"]

    assert engineering_profile.as_dict() == {}
    assert result["working_profile"]["extracted_params"] == {}


@pytest.mark.asyncio
async def test_parallel_path_partial_failure_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    def _deep_merge(base: dict, patch: dict) -> dict:
        merged = deepcopy(base)
        for key, value in patch.items():
            current = merged.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                merged[key] = _deep_merge(current, value)
            else:
                merged[key] = value
        return merged

    def _apply_patch(state: SealAIState, patch: dict) -> SealAIState:
        merged = _deep_merge(state.model_dump(exclude_none=False), patch)
        return SealAIState.model_validate(merged)

    def _raise_material(*_args, **_kwargs):
        raise RuntimeError("material branch crashed")

    def _fake_mechanical(*_args, **_kwargs):
        return {
            "working_profile": {
                "calc_results": {"v_surface_m_s": 2.5},
                "live_calc_tile": {
                    "status": "ok",
                    "v_surface_m_s": 2.5,
                    "parameters": {"pressure_bar": 16.0, "speed_rpm": 1500.0},
                },
            },
            "reasoning": {
                "phase": "calculation",
                "last_node": "node_p4_live_calc",
            },
        }

    monkeypatch.setattr(graph_module, "material_agent_node", _raise_material)
    monkeypatch.setattr(graph_module, "node_p4_live_calc", _fake_mechanical)

    state = SealAIState(
        conversation={
            "messages": [HumanMessage(content="Bitte neue Auslegung rechnen")],
            "intent": {"goal": "design_recommendation"},
        },
        working_profile={
            "engineering_profile": {
                "pressure_max_bar": 16.0,
                "rpm": 1500.0,
            },
            "extracted_params": {
                "pressure_max_bar": 16.0,
                "rpm": 1500.0,
            },
        },
        reasoning={"phase": "frontdoor", "last_node": "node_p1_context"},
    )

    material_patch = await graph_module._material_analysis_node(state)
    mechanical_patch = await graph_module._mechanical_analysis_node(state)
    state_after_material = _apply_patch(state, material_patch)
    state_after_branches = _apply_patch(state_after_material, mechanical_patch)
    merge_patch = graph_module._merge_analysis_node(state_after_branches)
    merged_state = _apply_patch(state_after_branches, merge_patch)
    response_patch = response_node(merged_state)

    assert merge_patch["system"]["error"] == "partial_expert_failure"
    assert merged_state.system.error == "partial_expert_failure"
    assert "Ein Teil der Experten-Analyse ist fehlgeschlagen" in str(response_patch["system"]["final_text"] or "")


def test_fast_brain_tool_error_handoff() -> None:
    class _FailingTool:
        name = "live_physics_tool"

        async def ainvoke(self, _args):
            raise RuntimeError("tool offline")

    class _SingleCallLLM:
        async def ainvoke(self, _messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "name": "live_physics_tool",
                        "args": {"shaft_diameter_mm": 100.0, "speed_rpm": 3000.0},
                    }
                ],
            )

    router = FastBrainRouter.__new__(FastBrainRouter)
    router.llm = None
    router.tools = [_FailingTool()]
    router._tool_by_name = {"live_physics_tool": router.tools[0]}
    router.llm_with_tools = _SingleCallLLM()

    result = asyncio.run(router.chat("Bitte Schnellberechnung", []))

    assert result["status"] == "handoff_to_langgraph"
    assert result["handoff_to_slow_brain"] is True
    assert result["route"] == "slow_brain"
    assert "technischer Probleme" in result["content"]
