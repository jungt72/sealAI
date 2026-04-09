from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent.graph import GraphState
from app.agent.graph.topology import build_governed_graph
from app.agent.state.models import GovernedSessionState


@pytest.mark.asyncio
async def test_structured_clarification_interrupts_instead_of_normal_completion() -> None:
    graph = build_governed_graph()

    raw = await graph.ainvoke(GraphState())

    assert "__interrupt__" in raw
    interrupts = list(raw["__interrupt__"])
    assert interrupts
    payload = interrupts[0].value
    assert payload["kind"] == "structured_clarification"
    assert payload["response_class"] == "structured_clarification"
    assert payload["message"]
    interrupted_state = GraphState.model_validate(payload["state"])
    assert interrupted_state.output_response_class == "structured_clarification"
    assert interrupted_state.output_reply == payload["message"]


@pytest.mark.asyncio
async def test_resume_command_routes_next_user_input_back_into_observed_state() -> None:
    graph = build_governed_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "clarification-resume"}}

    with patch(
        "app.agent.graph.nodes.evidence_node.retrieve_evidence",
        new_callable=AsyncMock,
        return_value=([], {}),
    ):
        first = await graph.ainvoke(GraphState(), config=config)
        assert "__interrupt__" in first

        resumed = await graph.ainvoke(
            Command(resume="Medium ist Wasser, 12 bar, 80°C."),
            config=config,
        )

    result = GraphState.model_validate(resumed)
    persisted = GovernedSessionState.model_validate(result.model_dump())

    assert result.output_response_class != "structured_clarification"
    assert persisted.observed.raw_extractions
    assert any(item.field_name == "medium" for item in persisted.observed.raw_extractions)
    assert any(item.field_name == "pressure_bar" for item in persisted.observed.raw_extractions)
    assert any(item.field_name == "temperature_c" for item in persisted.observed.raw_extractions)


@pytest.mark.asyncio
async def test_non_clarification_path_remains_normal_result() -> None:
    graph = build_governed_graph()
    state = GraphState(
        pending_message="Medium Wasser, 12 bar, 80°C",
        tenant_id="test_tenant",
    )

    with patch(
        "app.agent.graph.nodes.evidence_node.retrieve_evidence",
        new_callable=AsyncMock,
        return_value=([], {}),
    ):
        raw = await graph.ainvoke(state)

    assert "__interrupt__" not in raw
    result = GraphState.model_validate(raw)
    assert result.output_response_class == "governed_state_update"
