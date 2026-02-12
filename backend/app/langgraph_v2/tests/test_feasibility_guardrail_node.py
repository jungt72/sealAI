from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.nodes_guardrail import (
    feasibility_guardrail_node,
    feasibility_guardrail_router,
)
from app.langgraph_v2.state import SealAIState, TechnicalParameters


def test_guardrail_blocks_api682() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Bitte auslegen nach API 682 für die Dichtung.")],
    )

    patch = feasibility_guardrail_node(state)
    patched = state.model_copy(update=patch, deep=True)

    assert patch.get("awaiting_user_input") is True
    assert patch.get("ask_missing_request") is not None
    assert feasibility_guardrail_router(patched) == "ask_missing"
    assert "HUMAN_REQUIRED" in " ".join((patch["recommendation"].risk_hints or []))


def test_guardrail_blocks_hydrogen() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Wir fahren mit Wasserstoff bei 40 bar.")],
    )

    patch = feasibility_guardrail_node(state)
    patched = state.model_copy(update=patch, deep=True)

    assert patch.get("awaiting_user_input") is True
    assert patch.get("ask_missing_request") is not None
    assert feasibility_guardrail_router(patched) == "ask_missing"
    assert patch.get("flags", {}).get("risk_level") == "critical"


def test_guardrail_sets_critical_when_pv_near_limit() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Bitte fortfahren.")],
        parameters=TechnicalParameters(
            pressure_bar=10.0,
            speed_rpm=3000.0,
            shaft_diameter=70.0,
        ),
    )

    patch = feasibility_guardrail_node(state)

    assert patch.get("awaiting_user_input") is True
    assert patch.get("ask_missing_request") is not None
    assert patch.get("flags", {}).get("risk_level") == "critical"
    assert any("PV" in hint for hint in (patch["recommendation"].risk_hints or []))
