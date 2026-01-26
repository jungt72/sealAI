from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_autonomous
from app.langgraph_v2.state import SealAIState


def test_autonomous_supervisor_action_maps_knowledge_worker(monkeypatch) -> None:
    def fake_run_llm(*_args, **_kwargs) -> str:
        return '{"thought":"needs sources","action":"knowledge_worker","new_tasks":[]}'

    monkeypatch.setattr(nodes_autonomous, "run_llm", fake_run_llm)
    monkeypatch.setattr(nodes_autonomous, "get_model_tier", lambda _tier: "fake-model")

    state = SealAIState(messages=[HumanMessage(content="Wer ist Kyrolon?")])
    patch = nodes_autonomous.autonomous_supervisor_node(state)

    assert patch["next_action"] == "RUN_KNOWLEDGE"
