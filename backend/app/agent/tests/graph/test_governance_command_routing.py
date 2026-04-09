from __future__ import annotations

import pytest
from langgraph.types import Command

from app.agent.graph import GraphState
from app.agent.graph.nodes.governance_node import governance_routing_node
from app.agent.state.models import AssertedClaim, AssertedState


def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _state(
    *,
    analysis_cycle: int = 0,
    max_cycles: int = 3,
    blocking_unknowns: list[str] | None = None,
    conflict_flags: list[str] | None = None,
    **fields,
) -> GraphState:
    assertions = {
        field: _claim(field, val, conf)
        for field, (val, conf) in fields.items()
    }
    asserted = AssertedState(
        assertions=assertions,
        blocking_unknowns=blocking_unknowns or [],
        conflict_flags=conflict_flags or [],
    )
    return GraphState(
        asserted=asserted,
        analysis_cycle=analysis_cycle,
        max_cycles=max_cycles,
    )


@pytest.mark.asyncio
async def test_governance_routing_node_uses_command_goto_cycle_increment_for_continue_path() -> None:
    state = _state(
        medium=("Dampf", "confirmed"),
        pressure_bar=(12.0, "confirmed"),
        blocking_unknowns=["temperature_c"],
        analysis_cycle=1,
        max_cycles=3,
    )

    result = await governance_routing_node(state)

    assert isinstance(result, Command)
    assert result.goto == "cycle_increment"
    assert "governance" in result.update
    assert result.update["governance"].gov_class == "B"


@pytest.mark.asyncio
async def test_governance_routing_node_uses_command_goto_matching_for_terminate_path() -> None:
    state = _state(
        medium=("Dampf", "confirmed"),
        pressure_bar=(12.0, "confirmed"),
        temperature_c=(180.0, "confirmed"),
    )

    result = await governance_routing_node(state)

    assert isinstance(result, Command)
    assert result.goto == "matching"
    assert "governance" in result.update
    assert result.update["governance"].gov_class == "A"
