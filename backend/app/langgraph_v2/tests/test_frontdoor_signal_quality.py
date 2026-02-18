from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_frontdoor
from app.langgraph_v2.state import SealAIState


def test_frontdoor_emits_trace_prompt_fields(monkeypatch):
    monkeypatch.setattr(
        nodes_frontdoor,
        "run_llm",
        lambda **_kwargs: '{"intent": "design_recommendation", "parameters": {}}',
    )
    state = SealAIState(messages=[HumanMessage(content="Bitte nach DIN 376 prüfen.")])
    patch = nodes_frontdoor.frontdoor_discovery_node(state)

    assert patch.get("prompt_id_used") == "discovery/analysis"
    assert isinstance(patch.get("prompt_fingerprint"), str)
    assert patch.get("prompt_version_used")


def test_frontdoor_keeps_non_empty_reply_text(monkeypatch):
    monkeypatch.setattr(
        nodes_frontdoor,
        "run_llm",
        lambda **_kwargs: '{"intent": "design_recommendation"}',
    )
    state = SealAIState(messages=[HumanMessage(content="Quellen bitte.")])
    patch = nodes_frontdoor.frontdoor_discovery_node(state)

    assert (patch["working_memory"].frontdoor_reply or "").strip() != ""
