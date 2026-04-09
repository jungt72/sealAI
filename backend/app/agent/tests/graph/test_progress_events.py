from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.compute_node import compute_node
from app.agent.graph.nodes.evidence_node import evidence_node
from app.agent.graph.nodes.governance_node import governance_node
from app.agent.state.models import AssertedClaim, AssertedState


def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


@pytest.mark.asyncio
async def test_evidence_node_emits_evidence_retrieved_event() -> None:
    writer = []
    state = GraphState(
        tenant_id="tenant-1",
        asserted=AssertedState(
            assertions={"medium": _claim("medium", "Dampf")}
        ),
    )
    with (
        patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=([{"id": "card-1"}], {}),
        ),
        patch(
            "app.agent.graph.nodes.evidence_node.get_stream_writer",
            return_value=writer.append,
        ),
    ):
        result = await evidence_node(state)

    assert result.rag_evidence == [{"id": "card-1"}]
    assert writer == [{"event_type": "evidence_retrieved", "sources_count": 1}]


@pytest.mark.asyncio
async def test_compute_node_emits_compute_complete_event() -> None:
    writer = []
    state = GraphState(
        asserted=AssertedState(
            assertions={
                "shaft_diameter_mm": _claim("shaft_diameter_mm", 50.0),
                "speed_rpm": _claim("speed_rpm", 1500.0),
            }
        )
    )
    with patch(
        "app.agent.graph.nodes.compute_node.get_stream_writer",
        return_value=writer.append,
    ):
        result = await compute_node(state)

    assert result.compute_results
    assert writer
    assert writer[0]["event_type"] == "compute_complete"
    assert writer[0]["calc_type"] == "rwdr"
    assert "status" in writer[0]


@pytest.mark.asyncio
async def test_governance_node_emits_governance_ready_event() -> None:
    writer = []
    state = GraphState(
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Dampf"),
                "pressure_bar": _claim("pressure_bar", 12.0),
                "temperature_c": _claim("temperature_c", 180.0),
            }
        )
    )
    with patch(
        "app.agent.graph.nodes.governance_node.get_stream_writer",
        return_value=writer.append,
    ):
        result = await governance_node(state)

    assert result.governance.gov_class == "A"
    assert writer == [{"event_type": "governance_ready", "outward_class": "governed_state_update"}]
