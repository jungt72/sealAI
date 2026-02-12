from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_frontdoor
from app.langgraph_v2.state import SealAIState


def test_frontdoor_material_explanation_routes_to_knowledge_flags(monkeypatch) -> None:
    monkeypatch.setattr(nodes_frontdoor, "get_model_tier", lambda *_args, **_kwargs: "nano")
    monkeypatch.setattr(
        nodes_frontdoor,
        "run_llm",
        lambda **_kwargs: (
            '{"frontdoor_reply":"ok","intent":{"goal":"explanation_or_comparison","key":"knowledge_material","confidence":0.92}}'
        ),
    )

    state = SealAIState(messages=[HumanMessage(content="Explain PTFE and compare to NBR.")])
    patch = nodes_frontdoor.frontdoor_discovery_node(state)

    assert patch["intent"].goal == "explanation_or_comparison"
    assert patch["intent"].key == "knowledge_material"
    assert patch["knowledge_type"] == "material"
    assert patch["requires_rag"] is True
