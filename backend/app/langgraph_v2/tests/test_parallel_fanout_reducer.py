from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.langgraph_v2.sealai_graph_v2 import (
    _cluster_specialist_router,
    _merge_parallel_worker_outputs,
    _supervisor_fanout_dispatch,
    parallel_profile_worker_node,
    parallel_reducer_node,
    parallel_validation_worker_node,
)
from app.langgraph_v2.state import SealAIState


def test_send_fanout_enabled_returns_send_objects(monkeypatch) -> None:
    monkeypatch.setenv("LANGGRAPH_V2_PARALLEL_FANOUT", "1")
    state = SealAIState(flags={"parameters_complete_for_profile": True})

    sends = _supervisor_fanout_dispatch(state)

    assert isinstance(sends, list)
    assert len(sends) == 2
    assert all(isinstance(item, Send) for item in sends)
    assert [item.node for item in sends] == [
        "parallel_profile_worker",
        "parallel_validation_worker",
    ]
    assert sends[1].arg.get("flags", {}).get("parameters_complete_for_profile") is True


def test_parallel_reducer_merge_is_deterministic_for_out_of_order_results() -> None:
    profile_result = {
        "worker": "cluster_profile_node",
        "profile_choice": {"profile": "Radial", "confidence": "heuristic"},
    }
    validation_result = {
        "worker": "cluster_validation_node",
        "validation": {"status": "error", "issues": ["missing_pressure"]},
    }

    merged_a = _merge_parallel_worker_outputs([profile_result, validation_result])
    merged_b = _merge_parallel_worker_outputs([validation_result, profile_result])

    assert merged_a == merged_b
    assert merged_a["design_notes"]["profile"]["profile"] == "Radial"
    assert merged_a["design_notes"]["validation"]["status"] == "error"
    assert merged_a["errors"] == ["cluster_validation_node:missing_pressure"]


def test_parallel_fanout_disabled_keeps_sequential_path(monkeypatch) -> None:
    monkeypatch.delenv("LANGGRAPH_V2_PARALLEL_FANOUT", raising=False)
    state = SealAIState()

    assert _cluster_specialist_router(state) == "sequential"
    assert _supervisor_fanout_dispatch(state) == "sequential"


def test_parallel_fanout_executes_workers_and_reducer(monkeypatch) -> None:
    monkeypatch.setenv("LANGGRAPH_V2_PARALLEL_FANOUT", "1")

    def _entry(state: SealAIState) -> dict:
        return {"last_node": "cluster_material_node"}

    builder = StateGraph(SealAIState)
    builder.add_node("cluster_material_node", _entry)
    builder.add_node("parallel_profile_worker", parallel_profile_worker_node)
    builder.add_node("parallel_validation_worker", parallel_validation_worker_node)
    builder.add_node("parallel_reducer_node", parallel_reducer_node)
    builder.add_edge(START, "cluster_material_node")
    builder.add_conditional_edges("cluster_material_node", _supervisor_fanout_dispatch)
    builder.add_edge(["parallel_profile_worker", "parallel_validation_worker"], "parallel_reducer_node")
    builder.add_edge("parallel_reducer_node", END)

    graph = builder.compile()
    result = graph.invoke(SealAIState(flags={"parameters_complete_for_profile": True}))

    assert result["parallel_profile_result"].get("worker") == "cluster_profile_node"
    assert result["parallel_validation_result"].get("worker") == "cluster_validation_node"
    assert result["profile_choice"].get("profile") == "Radial-Doppellippendichtung"
    assert result["validation"].get("status") == "ok"
