import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_frontdoor
from app.langgraph_v2.state import Intent, SealAIState


def test_frontdoor_intent_parsing_handles_code_fences(monkeypatch):
    monkeypatch.setattr(
        nodes_frontdoor,
        "run_llm",
        lambda **_kwargs: "```json\n"
        + '{"intent": {"goal": "design_recommendation"}, "frontdoor_reply": "OK"}'
        + "\n```",
    )
    state = SealAIState(messages=[HumanMessage(content="Bitte Dichtung empfehlen")])
    result = nodes_frontdoor.frontdoor_discovery_node(state)
    intent = result["intent"]
    assert isinstance(intent, Intent)
    assert intent.goal == "design_recommendation"
    # assert intent.confidence == 0.9 # Field removed from Intent model
    assert (result["working_memory"].frontdoor_reply or "").strip() != ""


def test_frontdoor_intent_parsing_handles_text_plus_json(monkeypatch):
    monkeypatch.setattr(
        nodes_frontdoor,
        "run_llm",
        lambda **_kwargs: 'Sure, here is JSON:\n{"intent": "explanation_or_comparison", "frontdoor_reply": "OK"}',
    )
    state = SealAIState(messages=[HumanMessage(content="Was ist FKM?")])
    result = nodes_frontdoor.frontdoor_discovery_node(state)
    intent = result["intent"]
    assert intent.goal == "explanation_or_comparison"


def test_frontdoor_intent_parsing_missing_fields_defaults(monkeypatch):
    monkeypatch.setattr(nodes_frontdoor, "run_llm", lambda **_kwargs: "{}")
    state = SealAIState(messages=[HumanMessage(content="Bitte Dichtung empfehlen")])
    result = nodes_frontdoor.frontdoor_discovery_node(state)
    intent = result["intent"]
    assert intent.goal == "design_recommendation"
    # assert intent.confidence == 0.0 # Field removed


def test_frontdoor_smalltalk_greetings_bypass_llm(monkeypatch):
    called = False

    def _fail(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("LLM should not be called for greetings")

    monkeypatch.setattr(nodes_frontdoor, "run_llm", _fail)

    for greeting in ("Hallo", "Hi", "Grüß dich"):
        state = SealAIState(messages=[HumanMessage(content=greeting)])
        result = nodes_frontdoor.frontdoor_discovery_node(state)
        intent = result["intent"]
        assert intent.goal == "design_recommendation"
        # assert intent.confidence == 1.0 # Field removed

    assert called is True
