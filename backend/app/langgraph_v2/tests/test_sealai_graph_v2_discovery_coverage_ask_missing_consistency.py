import pytest

pytest.skip(
    "ask-missing flow is covered by the legacy graph which is no longer wired into the v2 frontdoor/supervisor topology",
    allow_module_level=True,
)

import asyncio
from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_discovery, nodes_resume
from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState


def test_discovery_low_coverage_triggers_ask_missing(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    monkeypatch.setattr(
        nodes_discovery,
        "run_llm",
        lambda **_kwargs: '{"summary": "Stub summary", "coverage": 0.3, "missing": ["pressure_bar"]}',
    )
    graph = asyncio.run(get_sealai_graph_v2())
    initial_state = {"messages": [HumanMessage(content="Pumpe leckt, brauche Hilfe")]}
    config = build_v2_config(thread_id="t1", user_id="u1")
    result = graph.invoke(initial_state, config=config)
    state = result if isinstance(result, SealAIState) else SealAIState.model_validate(result)

    assert state.ask_missing_request is not None
    assert state.ask_missing_scope in {"discovery", "technical"}


def test_resume_repairs_missing_request(monkeypatch):
    state = SealAIState(
        awaiting_user_input=True,
        ask_missing_request=None,
        missing_params=["pressure_bar", "temperature_max"],
        ask_missing_scope=None,
        messages=[HumanMessage(content="Noch keine Werte")],
    )
    updated = nodes_resume.resume_router_node(state)
    assert updated["ask_missing_request"] is not None
    assert updated["ask_missing_scope"] in {"technical", "discovery"}
