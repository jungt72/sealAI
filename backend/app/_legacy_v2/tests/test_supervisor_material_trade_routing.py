from langchain_core.messages import HumanMessage
from langgraph.types import Send

from app._legacy_v2.nodes.nodes_supervisor import supervisor_policy_node
from app._legacy_v2.state import Intent, SealAIState


def test_supervisor_trade_name_forces_material_agent_route() -> None:
    state = SealAIState(
        intent=Intent(goal="smalltalk", confidence=0.4, high_impact_gaps=[]),
        messages=[HumanMessage(content="Was kannst du mir ueber Kyrolon sagen?")],
    )

    command = supervisor_policy_node(state)

    assert command.update["requires_rag"] is True
    assert command.update["need_sources"] is True
    assert command.update["intent"].goal == "explanation_or_comparison"
    assert isinstance(command.goto, list)
    assert any(isinstance(item, Send) and item.node == "material_agent" for item in command.goto)


def test_supervisor_parallel_send_from_frontdoor_flags() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation", confidence=0.9, high_impact_gaps=[]),
        flags={
            "frontdoor_intent_category": "ENGINEERING_CALCULATION",
            "is_safety_critical": True,
            "needs_pricing": True,
        },
        requires_rag=True,
        need_sources=True,
    )

    command = supervisor_policy_node(state)

    assert isinstance(command.goto, list)
    routed = {item.node for item in command.goto if isinstance(item, Send)}
    assert "material_agent" in routed
    assert "pricing_agent" in routed
    assert "safety_agent" in routed
    assert "calculator_agent" in routed
