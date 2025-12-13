from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_intent
from app.langgraph_v2.state import Intent, SealAIState


def test_intent_parsing_handles_code_fences(monkeypatch):
    monkeypatch.setattr(
        nodes_intent,
        "run_llm",
        lambda **_kwargs: "```json\n{\"key\": \"consulting_preflight\", \"confidence\": 0.9}\n```",
    )
    state = SealAIState(messages=[HumanMessage(content="Bitte Dichtung empfehlen")])
    result = nodes_intent.intent_projector_node(state)
    intent = result["intent"]
    assert isinstance(intent, Intent)
    assert intent.key == "consulting_preflight"
    assert intent.confidence == 0.9


def test_intent_parsing_handles_text_plus_json(monkeypatch):
    monkeypatch.setattr(
        nodes_intent,
        "run_llm",
        lambda **_kwargs: 'Sure, here is JSON:\n{"key": "knowledge_material", "confidence": 0.6}',
    )
    state = SealAIState(messages=[HumanMessage(content="Was ist FKM?")])
    result = nodes_intent.intent_projector_node(state)
    intent = result["intent"]
    assert intent.key == "knowledge_material"
    assert intent.confidence == 0.6


def test_intent_parsing_missing_fields_defaults(monkeypatch):
    monkeypatch.setattr(
        nodes_intent,
        "run_llm",
        lambda **_kwargs: "{}",
    )
    state = SealAIState(messages=[HumanMessage(content="Hallo!")])
    result = nodes_intent.intent_projector_node(state)
    intent = result["intent"]
    assert intent.key == "smalltalk"
    assert intent.confidence == 1.0


def test_intent_smalltalk_greetings_bypass_llm(monkeypatch):
    called = False

    def _fail(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("LLM should not be called for greetings")

    monkeypatch.setattr(nodes_intent, "run_llm", _fail)

    for greeting in ("Hallo", "Hi", "Grüß dich"):
        state = SealAIState(messages=[HumanMessage(content=greeting)])
        result = nodes_intent.intent_projector_node(state)
        intent = result["intent"]
        assert intent.key == "smalltalk"
        assert intent.confidence == 1.0

    assert called is False
