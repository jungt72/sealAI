from langchain_core.messages import HumanMessage

from app.langgraph.compile import _is_technical_consulting, _route_after_intent
from app.langgraph.nodes.bedarfsanalyse_agent import bedarfsanalyse_node
from app.langgraph.state import SealAIState


def test_route_starts_with_rapport_for_technical_intent():
    state = SealAIState(
        slots={"user_query": "Bitte analysiere eine Radialwellendichtung."},
        intent={"kind": "technical_consulting", "domain": "sealing", "confidence": 0.92},
    )
    assert _route_after_intent(state) == "rapport_agent"


def test_route_transitions_to_warmup_when_rapport_done():
    state = SealAIState(
        slots={
            "user_query": "Bitte analysiere eine Radialwellendichtung.",
            "rapport_phase_done": True,
        },
        intent={"kind": "technical_consulting", "domain": "sealing", "confidence": 0.92},
    )
    assert _route_after_intent(state) == "warmup_agent"


def test_route_skips_bedarfsanalyse_for_simple_direct_tasks():
    state = SealAIState(
        slots={
            "user_query": "Zähle die Zahlen 1 bis 5 auf.",
            "task_mode_hint": "simple_direct_output",
        },
        intent={"kind": "technical_consulting", "domain": "sealing", "confidence": 0.92},
    )
    assert _route_after_intent(state) == "context_retrieval"


def test_smalltalk_intent_never_counts_as_technical():
    intent = {"kind": "greeting", "domain": "none", "confidence": 0.95}
    assert _is_technical_consulting(intent) is False


def test_smalltalk_routing_goes_to_context_path():
    intent = {"kind": "smalltalk", "domain": "none", "confidence": 0.95}
    state = SealAIState(slots={"user_query": "hallo, wie geht es dir?"}, intent=intent)
    assert _route_after_intent(state) == "context_retrieval"


def test_low_confidence_technical_intent_does_not_trigger_bedarfsanalyse():
    intent = {"kind": "technical_consulting", "domain": "sealing", "confidence": 0.62}
    state = SealAIState(slots={"user_query": "Welches Profil?"}, intent=intent)
    assert _route_after_intent(state) == "context_retrieval"


def test_bedarfsanalyse_node_skips_state_for_smalltalk_intents():
    initial = SealAIState(
        slots={"user_query": "hallo, wie geht es dir?"},
        messages=[HumanMessage(content="hallo, wie geht es dir?", id="m-user")],
        intent={"kind": "greeting", "domain": "none", "confidence": 0.95},
        bedarfsanalyse={"phase": "existing"},
    )
    result = bedarfsanalyse_node(initial, config={"configurable": {}})
    assert isinstance(result, dict)
    slots = result.get("slots") or {}
    assert isinstance(slots.get("requirements"), str)
    assert slots.get("requirements") or result.get("message_out")
    assert initial["bedarfsanalyse"]["phase"] == "existing"
