import pytest

pytest.skip(
    "ask-missing flow is covered by the legacy graph which is no longer wired into the v2 frontdoor/supervisor topology",
    allow_module_level=True,
)

import asyncio
from langchain_core.messages import HumanMessage

from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.nodes import nodes_intent, nodes_discovery


def test_sealai_graph_v2_ask_missing_flow(monkeypatch):
    # Use in-memory checkpointer and stubbed LLM responses to avoid network calls.
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")

    # Stub discovery summary to low coverage so ask-missing is triggered.
    monkeypatch.setattr(
        nodes_discovery,
        "run_llm",
        lambda **_kwargs: '{"summary": "Stub summary", "coverage": 0.2, "missing": ["pressure_bar", "temperature_max"]}',
    )
    # Force intent to consulting flow.
    monkeypatch.setattr(
        nodes_intent,
        "run_llm",
        lambda **_kwargs: '{"key": "consulting_preflight", "confidence": 1.0}',
    )

    graph = asyncio.run(get_sealai_graph_v2())
    initial_state = {"messages": [HumanMessage(content="Mein Getriebe leckt, brauche Dichtungsempfehlung")]}
    config = build_v2_config(thread_id="test-thread", user_id="test-user", tenant_id="tenant-1")

    result = graph.invoke(initial_state, config=config)
    state = result if isinstance(result, SealAIState) else SealAIState.model_validate(result)

    assert state.awaiting_user_input is True
    assert state.ask_missing_request is not None
    assert state.ask_missing_scope in {"technical", "discovery"}
    assert state.missing_params  # should list missing technical params
