import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from langchain_core.messages import AIMessage, HumanMessage

from app.langgraph_v2.nodes import nodes_frontdoor
from app.langgraph_v2.nodes.nodes_frontdoor import FrontdoorRouteAxesOutput
from app.langgraph_v2.state import SealAIState


def _run_with_fake_structured(state: SealAIState, fake_output: FrontdoorRouteAxesOutput) -> dict:
    def _fake_structured(_state: SealAIState, _user_text: str) -> FrontdoorRouteAxesOutput:
        return fake_output

    original = nodes_frontdoor._invoke_frontdoor_structured
    nodes_frontdoor._invoke_frontdoor_structured = _fake_structured
    try:
        return nodes_frontdoor.frontdoor_discovery_node(state)
    finally:
        nodes_frontdoor._invoke_frontdoor_structured = original


def test_frontdoor_structured_maps_general_knowledge() -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="Was ist FKM?")]})
    result = _run_with_fake_structured(
        state,
        FrontdoorRouteAxesOutput(
            social_opening=False,
            task_intents=["general_knowledge"],
            is_safety_critical=False,
            requires_rag=False,
            needs_pricing=False,
            reasoning="The request asks for a generic explanation.",
        ),
    )

    assert result["conversation"]["intent"].goal == "explanation_or_comparison"
    assert result["reasoning"]["requires_rag"] is False
    assert result["reasoning"]["flags"]["frontdoor_bypass_supervisor"] is False


def test_frontdoor_structured_chitchat_sets_bypass_flag() -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="Hallo")]})
    result = _run_with_fake_structured(
        state,
        FrontdoorRouteAxesOutput(
            social_opening=True,
            task_intents=[],
            is_safety_critical=False,
            requires_rag=False,
            needs_pricing=False,
            reasoning="The input is a greeting without a technical objective.",
        ),
    )

    assert result["conversation"]["intent"] == "smalltalk"
    assert result["reasoning"]["flags"]["frontdoor_bypass_supervisor"] is True


def test_frontdoor_structured_material_research_forces_rag() -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="Was weißt du über Kyrolon?")]})
    result = _run_with_fake_structured(
        state,
        FrontdoorRouteAxesOutput(
            social_opening=False,
            task_intents=["material_research"],
            is_safety_critical=False,
            requires_rag=True,
            needs_pricing=False,
            reasoning="The request is about a specific trade-name material.",
        ),
    )

    assert result["conversation"]["intent"].goal == "explanation_or_comparison"
    assert result["reasoning"]["requires_rag"] is True
    assert result["reasoning"]["need_sources"] is True


def test_frontdoor_fallback_keeps_material_trade_query_on_material_research(monkeypatch) -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="Was kannst du mir ueber Kyrolon sagen?")]})

    def _raise(_state: SealAIState, _user_text: str) -> FrontdoorRouteAxesOutput:
        raise RuntimeError("structured output unavailable")

    monkeypatch.setattr(nodes_frontdoor, "_invoke_frontdoor_structured", _raise)

    result = nodes_frontdoor.frontdoor_discovery_node(state)

    assert result["conversation"]["intent"].goal == "explanation_or_comparison"
    assert result["reasoning"]["requires_rag"] is True
    assert result["reasoning"]["need_sources"] is True
    assert result["reasoning"]["flags"]["frontdoor_intent_category"] == "MATERIAL_RESEARCH"


def test_frontdoor_fallback_keeps_engineering_query_on_engineering_intake(monkeypatch) -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="RWDR 50 mm, 3000 rpm, 5 bar, 120 C")]})

    def _raise(_state: SealAIState, _user_text: str) -> FrontdoorRouteAxesOutput:
        raise RuntimeError("structured output unavailable")

    monkeypatch.setattr(nodes_frontdoor, "_invoke_frontdoor_structured", _raise)

    result = nodes_frontdoor.frontdoor_discovery_node(state)

    assert result["conversation"]["intent"].goal == "design_recommendation"
    assert result["reasoning"]["requires_rag"] is False
    assert result["reasoning"]["flags"]["frontdoor_intent_category"] == "ENGINEERING_CALCULATION"


def test_frontdoor_structured_maps_extracted_parameters() -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="120 bar, 85C, Medium H2")]})
    result = _run_with_fake_structured(
        state,
        FrontdoorRouteAxesOutput(
            social_opening=False,
            task_intents=["engineering_calculation"],
            is_safety_critical=True,
            requires_rag=False,
            needs_pricing=False,
            extracted_parameters={"pressure_bar": 120.0, "temperature_c": 85.0, "medium": "H2"},
            reasoning="The request provides engineering operating parameters.",
        ),
    )

    params = result["working_profile"]["engineering_profile"]
    extracted = result["working_profile"]["extracted_params"]
    assert params.as_dict() == {}
    assert extracted["pressure_bar"] == 120.0
    assert extracted["temperature_C"] == 85.0
    assert extracted["medium"] == "H2"
    assert result["reasoning"]["extracted_parameter_provenance"]["pressure_bar"] == "frontdoor_extracted"
    assert result["reasoning"]["extracted_parameter_identity"]["medium"]["identity_class"] == "confirmed"
    assert result["reasoning"]["extracted_parameter_identity"]["medium"]["normalized_value"] == "hydrogen"
    assert result["reasoning"]["flags"]["is_safety_critical"] is True


def test_frontdoor_social_opening_with_task_intent_does_not_bypass() -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="Hi, kannst du bitte 120 bar auslegen?")]})
    result = _run_with_fake_structured(
        state,
        FrontdoorRouteAxesOutput(
            social_opening=True,
            task_intents=["engineering_calculation"],
            is_safety_critical=False,
            requires_rag=False,
            needs_pricing=False,
            reasoning="Social opener with explicit engineering request.",
        ),
    )

    assert result["reasoning"]["flags"]["frontdoor_social_opening"] is True
    assert result["reasoning"]["flags"]["frontdoor_task_intents"] == ["engineering_calculation"]
    assert result["reasoning"]["flags"]["frontdoor_bypass_supervisor"] is False


def test_frontdoor_technical_cue_veto_forces_supervisor() -> None:
    state = SealAIState(conversation={"messages": [HumanMessage(content="Hi there, PTFE sounds great.")]})
    result = _run_with_fake_structured(
        state,
        FrontdoorRouteAxesOutput(
            social_opening=True,
            task_intents=[],
            is_safety_critical=False,
            requires_rag=False,
            needs_pricing=False,
            reasoning="Looks social only.",
        ),
    )

    assert result["reasoning"]["flags"]["frontdoor_social_opening"] is True
    assert result["reasoning"]["flags"]["frontdoor_bypass_supervisor"] is False
    assert result["reasoning"]["flags"]["frontdoor_technical_cue_veto"] is True
    assert "PTFE" in result["reasoning"]["flags"]["frontdoor_technical_cue_matches"]


def test_build_frontdoor_messages_truncates_to_last_two_turns() -> None:
    state = SealAIState(
        conversation={
            "messages": [
                HumanMessage(content="H1"),
                AIMessage(content="A1"),
                HumanMessage(content="H2"),
                AIMessage(content="A2"),
                HumanMessage(content="H3"),
            ]
        }
    )
    built_messages = nodes_frontdoor._build_frontdoor_messages(state, "H3")
    history_contents = [msg.content for msg in built_messages[1:]]

    assert history_contents == ["H2", "A2", "H3"]
