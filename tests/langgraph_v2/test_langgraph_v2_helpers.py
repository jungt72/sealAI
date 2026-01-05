from langchain_core.messages import AIMessage

from app.api.v1.endpoints import langgraph_v2
from app.langgraph.io import AskMissingRequest
from app.langgraph_v2.constants import CHECKPOINTER_NAMESPACE_V2
from app.langgraph_v2.sealai_graph_v2 import build_v2_config
from app.langgraph_v2.state import Recommendation, SealAIState


def test_extract_final_answer_prefers_final_text():
    state = SealAIState(final_text="Final answer", messages=[AIMessage(content="ignored")])

    result = langgraph_v2._extract_final_answer_from_state(state)

    assert result == "Final answer"


def test_extract_final_answer_uses_ai_message_when_needed():
    state = SealAIState(messages=[AIMessage(content=[{"type": "text", "text": "Hallo Welt"}])])

    result = langgraph_v2._extract_final_answer_from_state(state)

    assert result == "Hallo Welt"


def test_extract_final_answer_uses_recommendation():
    recommendation = Recommendation(summary="Use PTFE", rationale="High temperature")
    state = SealAIState(recommendation=recommendation)

    result = langgraph_v2._extract_final_answer_from_state(state)

    assert result == "Use PTFE"


def test_extract_final_answer_uses_working_memory():
    state = SealAIState(working_memory={"knowledge_generic": "Knowledge fallback"})

    result = langgraph_v2._extract_final_answer_from_state(state)

    assert result == "Knowledge fallback"


def test_extract_final_answer_has_fallback():
    state = SealAIState()

    result = langgraph_v2._extract_final_answer_from_state(state)

    assert result == langgraph_v2._FALLBACK_ANSWER


def test_build_v2_config_sets_namespace_and_ids():
    cfg = build_v2_config(thread_id="thread-123", user_id="user-abc")

    assert cfg["configurable"]["thread_id"] == "thread-123"
    assert cfg["configurable"]["user_id"] == "user-abc"
    assert cfg["configurable"]["checkpoint_ns"] == CHECKPOINTER_NAMESPACE_V2


def test_build_ask_missing_payload_prefers_request_question():
    ask_request = AskMissingRequest(missing_fields=["pressure"], question="Bitte Druck angeben.")
    state = SealAIState(ask_missing_request=ask_request, missing_params=["pressure"], awaiting_user_input=True)

    payload = langgraph_v2._build_ask_missing_payload(state)

    assert payload["type"] == "ask_missing"
    assert payload["scope"] == "technical"
    assert payload["message"] == "Bitte Druck angeben."
    assert payload["request"]["missing_fields"] == ["pressure"]
